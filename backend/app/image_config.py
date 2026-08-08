from __future__ import annotations

import json
from typing import Any

from app.config import Settings


PROCESSING_SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "settings": {
            "type": "object",
            "properties": {
                "style_id": {
                    "type": "string",
                    "enum": ["centerline", "high_detail"],
                },
                "sensitivity": {"type": "number", "minimum": 0.05, "maximum": 0.95},
                "noise_filter": {"type": "integer", "minimum": 0, "maximum": 10},
                "simplify_tolerance": {"type": "number", "minimum": 0, "maximum": 8},
            },
            "required": ["style_id", "sensitivity", "noise_filter", "simplify_tolerance"],
            "additionalProperties": False,
        },
        "assistant_message": {"type": "string"},
    },
    "required": ["settings", "assistant_message"],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """You configure an OpenCV slab-vein extraction pipeline for CNC DXF output.
Return only JSON. Choose safe settings from the user's natural-language request.
Use centerline for clean, continuous CNC toolpaths and high_detail for faint,
low-contrast, or highly branched veins.
Higher sensitivity finds more veins. Higher noise_filter removes specks. Higher
simplify_tolerance makes fewer, smoother DXF points."""


def plan_processing_settings(message: str, settings: Settings) -> tuple[dict[str, Any], str]:
    gemini_plan = _try_gemini_settings(message, settings)
    if gemini_plan is not None:
        return gemini_plan
    openai_plan = _try_openai_settings(message, settings)
    if openai_plan is not None:
        return openai_plan
    recommended = recommend_processing_settings(message)
    return recommended, _fallback_message(recommended)


def recommend_processing_settings(message: str) -> dict[str, Any]:
    text = message.lower()
    recommendation: dict[str, Any] = {
        "style_id": "centerline",
        "sensitivity": 0.64,
        "noise_filter": 2,
        "simplify_tolerance": 1.6,
    }
    if any(token in text for token in ["faint", "low contrast", "more detail", "thin", "weak", "nhạt", "mờ"]):
        recommendation.update(
            {"style_id": "high_detail", "sensitivity": 0.76, "noise_filter": 3, "simplify_tolerance": 0.9}
        )
    if any(token in text for token in ["too noisy", "clean", "less detail", "remove specks", "smooth", "sạch", "nhiễu"]):
        recommendation.update({"sensitivity": 0.48, "noise_filter": 6, "simplify_tolerance": 2.4})
    if any(token in text for token in ["outline", "pocket", "contour", "closed", "biên", "viền"]):
        recommendation.update({"style_id": "centerline", "sensitivity": 0.64, "noise_filter": 4, "simplify_tolerance": 2.2})
    if any(token in text for token in ["green", "magenta", "overlay", "marked", "color", "màu", "đánh dấu"]):
        recommendation.update({"style_id": "high_detail", "sensitivity": 0.58, "noise_filter": 2, "simplify_tolerance": 0.8})
    return recommendation


def _try_openai_settings(message: str, settings: Settings) -> tuple[dict[str, Any], str] | None:
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
                    "content": f"Image configuration request: {message}\nReturn JSON matching: {json.dumps(PROCESSING_SETTINGS_SCHEMA)}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        return _parse_settings_plan(content)
    except Exception:
        return None


def _try_gemini_settings(message: str, settings: Settings) -> tuple[dict[str, Any], str] | None:
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Return JSON matching this schema: {json.dumps(PROCESSING_SETTINGS_SCHEMA)}\n\n"
            f"Image configuration request: {message}"
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
        return _parse_settings_plan(content)
    except Exception:
        return None


def _parse_settings_plan(content: str) -> tuple[dict[str, Any], str] | None:
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        return None
    raw_settings = parsed.get("settings")
    if not isinstance(raw_settings, dict):
        return None
    clean = {
        "style_id": str(raw_settings.get("style_id") or "centerline"),
        "sensitivity": _clamp_float(raw_settings.get("sensitivity"), 0.05, 0.95, 0.64),
        "noise_filter": int(_clamp_float(raw_settings.get("noise_filter"), 0, 10, 2)),
        "simplify_tolerance": _clamp_float(raw_settings.get("simplify_tolerance"), 0, 8, 1.6),
    }
    if clean["style_id"] not in {"centerline", "high_detail"}:
        clean["style_id"] = "centerline"
    return clean, str(parsed.get("assistant_message") or _fallback_message(clean))


def _fallback_message(settings: dict[str, Any]) -> str:
    return (
        "I updated the extraction settings for "
        f"{settings['style_id'].replace('_', ' ')} tracing: "
        f"sensitivity {settings['sensitivity']:.0%}, noise filter {settings['noise_filter']}, "
        f"simplify {settings['simplify_tolerance']:.1f}px."
    )


def _clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)
