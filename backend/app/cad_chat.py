from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

import cv2
import ezdxf
import numpy as np
from ezdxf.document import Drawing

from app.config import Settings

Action = dict[str, Any]


ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["add_border", "smooth", "translate", "scale"],
                    },
                    "amount_mm": {"type": "number"},
                    "dx_mm": {"type": "number"},
                    "dy_mm": {"type": "number"},
                    "factor": {"type": "number"},
                    "tolerance_mm": {"type": "number"},
                    "target_layer": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["type"],
                "additionalProperties": False,
            },
        },
        "assistant_message": {"type": "string"},
    },
    "required": ["actions", "assistant_message"],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """You are a careful CAD assistant for CNC stone slab vein drawings.
Return only JSON. Convert the user's request into safe DXF edit actions.
Allowed actions:
- add_border: amount_mm
- smooth: tolerance_mm
- translate: dx_mm and dy_mm
- scale: factor
If the request is ambiguous, return no actions and ask a concise clarification in assistant_message.
Never invent machining parameters beyond the user's request."""


def plan_dxf_actions(message: str, settings: Settings) -> tuple[list[Action], str]:
    gemini_plan = _try_gemini_plan(message, settings)
    if gemini_plan is not None:
        return gemini_plan
    llm_plan = _try_openai_plan(message, settings)
    if llm_plan is not None:
        return llm_plan
    return _fallback_plan(message)


def apply_dxf_actions(
    *,
    source_dxf: Path,
    job_dir: Path,
    revision_id: str,
    actions: list[Action],
) -> tuple[Path, Path, str]:
    revision_dir = job_dir / "revisions"
    revision_dir.mkdir(parents=True, exist_ok=True)
    output_dxf = revision_dir / f"{revision_id}.dxf"
    output_preview = revision_dir / f"{revision_id}.png"

    doc = ezdxf.readfile(source_dxf)
    summaries: list[str] = []
    for action in actions:
        action_type = action.get("type")
        if action_type == "add_border":
            amount = _positive_float(action.get("amount_mm"), default=10.0)
            _add_border(doc, amount)
            summaries.append(f"Added {amount:g} mm border")
        elif action_type == "smooth":
            tolerance = _positive_float(action.get("tolerance_mm"), default=2.0)
            changed = _smooth_polylines(doc, tolerance)
            summaries.append(f"Smoothed {changed} polylines at {tolerance:g} mm tolerance")
        elif action_type == "translate":
            dx = float(action.get("dx_mm") or 0.0)
            dy = float(action.get("dy_mm") or 0.0)
            changed = _translate_polylines(doc, dx, dy, action.get("target_layer"))
            summaries.append(f"Moved {changed} polylines by {dx:g}, {dy:g} mm")
        elif action_type == "scale":
            factor = _positive_float(action.get("factor"), default=1.0)
            changed = _scale_polylines(doc, factor)
            summaries.append(f"Scaled {changed} polylines by {factor:g}x")

    doc.saveas(output_dxf)
    render_dxf_preview(output_dxf, output_preview)
    return output_dxf, output_preview, "; ".join(summaries) if summaries else "No DXF edits were applied"


def render_dxf_preview(dxf_path: Path, output_path: Path) -> None:
    doc = ezdxf.readfile(dxf_path)
    polylines = _collect_polylines(doc)
    canvas_w, canvas_h = 1200, 760
    canvas = np.full((canvas_h, canvas_w, 3), 250, dtype=np.uint8)
    if not polylines:
        cv2.imwrite(str(output_path), canvas)
        return

    xs = [point[0] for item in polylines for point in item["points"]]
    ys = [point[1] for item in polylines for point in item["points"]]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    padding = 42
    scale = min((canvas_w - padding * 2) / span_x, (canvas_h - padding * 2) / span_y)

    for item in polylines:
        layer = item["layer"]
        color = (42, 140, 88) if layer != "AI_EDITS" else (35, 111, 218)
        points = []
        for x, y in item["points"]:
            px = int((x - min_x) * scale + padding)
            py = int(canvas_h - ((y - min_y) * scale + padding))
            points.append([px, py])
        if len(points) >= 2:
            cv2.polylines(canvas, [np.array(points, dtype=np.int32)], False, color, 2, cv2.LINE_AA)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), canvas)


def _try_openai_plan(message: str, settings: Settings) -> tuple[list[Action], str] | None:
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"User CAD edit request: {message}\nReturn JSON matching this schema: {json.dumps(ACTION_SCHEMA)}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        actions = parsed.get("actions") if isinstance(parsed, dict) else []
        assistant_message = parsed.get("assistant_message") if isinstance(parsed, dict) else None
        if isinstance(actions, list):
            return actions, str(assistant_message or "I prepared the requested CAD edit.")
    except Exception:
        return None
    return None


def _try_gemini_plan(message: str, settings: Settings) -> tuple[list[Action], str] | None:
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Return JSON matching this schema: {json.dumps(ACTION_SCHEMA)}\n\n"
            f"User CAD edit request: {message}"
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        content = getattr(response, "text", None) or "{}"
        parsed = json.loads(content)
        actions = parsed.get("actions") if isinstance(parsed, dict) else []
        assistant_message = parsed.get("assistant_message") if isinstance(parsed, dict) else None
        if isinstance(actions, list):
            return actions, str(assistant_message or "I prepared the requested CAD edit.")
    except Exception:
        return None
    return None


def _fallback_plan(message: str) -> tuple[list[Action], str]:
    text = message.lower()
    amount = _first_number(text)
    actions: list[Action] = []

    if "border" in text:
        actions.append({"type": "add_border", "amount_mm": amount or 10})
    elif "smooth" in text or "simplify" in text:
        actions.append({"type": "smooth", "tolerance_mm": amount or 2})
    elif "scale" in text:
        factor = amount if amount and amount > 0 else 1.05
        if "%" in text and amount:
            factor = 1 + amount / 100
        actions.append({"type": "scale", "factor": factor})
    elif "move" in text or "shift" in text or "translate" in text or "offset" in text:
        delta = amount or 5
        dx = 0.0
        dy = 0.0
        if "left" in text:
            dx = -delta
        elif "right" in text:
            dx = delta
        elif "down" in text:
            dy = -delta
        elif "up" in text:
            dy = delta
        else:
            return [], "Tell me which direction to move the geometry, for example: move the veins right by 5mm."
        actions.append({"type": "translate", "dx_mm": dx, "dy_mm": dy})
    else:
        return [], "I can apply edits such as add a border, smooth lines, scale, or move geometry by a set distance."

    return actions, "I prepared a structured CAD edit and generated a new DXF revision."


def _collect_polylines(doc: Drawing) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entity in doc.modelspace():
        if entity.dxftype() == "LWPOLYLINE":
            points = [(float(point[0]), float(point[1])) for point in entity.get_points("xy")]
            if len(points) >= 2:
                items.append({"entity": entity, "points": points, "layer": entity.dxf.layer})
        elif entity.dxftype() == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            items.append(
                {
                    "entity": entity,
                    "points": [(float(start.x), float(start.y)), (float(end.x), float(end.y))],
                    "layer": entity.dxf.layer,
                }
            )
    return items


def _add_border(doc: Drawing, amount_mm: float) -> None:
    polylines = _collect_polylines(doc)
    if not polylines:
        return
    xs = [point[0] for item in polylines for point in item["points"]]
    ys = [point[1] for item in polylines for point in item["points"]]
    min_x, max_x = min(xs) - amount_mm, max(xs) + amount_mm
    min_y, max_y = min(ys) - amount_mm, max(ys) + amount_mm
    layer = "AI_EDITS"
    if layer not in doc.layers:
        doc.layers.add(layer, color=5)
    doc.modelspace().add_lwpolyline(
        [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y), (min_x, min_y)],
        dxfattribs={"layer": layer, "color": 5},
    )


def _smooth_polylines(doc: Drawing, tolerance_mm: float) -> int:
    changed = 0
    for entity in doc.modelspace().query("LWPOLYLINE"):
        points = [(float(point[0]), float(point[1])) for point in entity.get_points("xy")]
        if len(points) < 4:
            continue
        simplified = _rdp(points, tolerance_mm)
        if len(simplified) >= 2 and len(simplified) < len(points):
            entity.set_points(simplified, format="xy")
            changed += 1
    return changed


def _translate_polylines(doc: Drawing, dx: float, dy: float, target_layer: str | None = None) -> int:
    changed = 0
    for entity in doc.modelspace().query("LWPOLYLINE"):
        if target_layer and entity.dxf.layer != target_layer:
            continue
        points = [(float(point[0]) + dx, float(point[1]) + dy) for point in entity.get_points("xy")]
        entity.set_points(points, format="xy")
        changed += 1
    return changed


def _scale_polylines(doc: Drawing, factor: float) -> int:
    if factor <= 0:
        return 0
    polylines = list(doc.modelspace().query("LWPOLYLINE"))
    points = [(float(point[0]), float(point[1])) for entity in polylines for point in entity.get_points("xy")]
    if not points:
        return 0
    cx = sum(point[0] for point in points) / len(points)
    cy = sum(point[1] for point in points) / len(points)
    for entity in polylines:
        scaled = [
            (cx + (float(point[0]) - cx) * factor, cy + (float(point[1]) - cy) * factor)
            for point in entity.get_points("xy")
        ]
        entity.set_points(scaled, format="xy")
    return len(polylines)


def _rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    index = 0
    max_distance = 0.0
    for i in range(1, len(points) - 1):
        distance = _perpendicular_distance(points[i], start, end)
        if distance > max_distance:
            index = i
            max_distance = distance
    if max_distance > epsilon:
        left = _rdp(points[: index + 1], epsilon)
        right = _rdp(points[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def _perpendicular_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    if start == end:
        return math.dist(point, start)
    numerator = abs((end[1] - start[1]) * point[0] - (end[0] - start[0]) * point[1] + end[0] * start[1] - end[1] * start[0])
    denominator = math.dist(start, end)
    return numerator / denominator


def _first_number(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _positive_float(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
