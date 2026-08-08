from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import ezdxf

from app.cad_chat import apply_dxf_actions, render_dxf_preview
from app.config import Settings
from app.image_config import recommend_processing_settings
from app.pipeline.processing import load_manifest


def inspect_dxf_job(settings: Settings, job_id: str) -> dict[str, Any]:
    manifest = load_manifest(settings, job_id)
    if manifest is None:
        raise ValueError("Job not found.")
    dxf_path = Path(manifest.dxf_path)
    if not dxf_path.exists():
        raise ValueError("DXF file not found.")

    doc = ezdxf.readfile(dxf_path)
    layers: dict[str, int] = {}
    entity_count = 0
    for entity in doc.modelspace():
        entity_count += 1
        layer = entity.dxf.layer
        layers[layer] = layers.get(layer, 0) + 1

    return {
        "job_id": job_id,
        "dxf_path": str(dxf_path),
        "entity_count": entity_count,
        "layers": layers,
        "metrics": manifest.metrics.model_dump(),
    }


def apply_cad_action(settings: Settings, job_id: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = load_manifest(settings, job_id)
    if manifest is None:
        raise ValueError("Job not found.")
    revision_id = uuid.uuid4().hex
    job_dir = settings.storage_dir / "jobs" / job_id
    dxf_path, preview_path, summary = apply_dxf_actions(
        source_dxf=Path(manifest.dxf_path),
        job_dir=job_dir,
        revision_id=revision_id,
        actions=actions,
    )
    return {
        "job_id": job_id,
        "revision_id": revision_id,
        "summary": summary,
        "dxf_path": str(dxf_path),
        "preview_path": str(preview_path),
        "dxf_url": f"/storage/jobs/{job_id}/revisions/{revision_id}.dxf",
        "preview_url": f"/storage/jobs/{job_id}/revisions/{revision_id}.png",
    }


def add_border_tool(settings: Settings, job_id: str, amount_mm: float) -> dict[str, Any]:
    return apply_cad_action(settings, job_id, [{"type": "add_border", "amount_mm": amount_mm}])


def smooth_tool(settings: Settings, job_id: str, tolerance_mm: float) -> dict[str, Any]:
    return apply_cad_action(settings, job_id, [{"type": "smooth", "tolerance_mm": tolerance_mm}])


def move_geometry_tool(settings: Settings, job_id: str, dx_mm: float, dy_mm: float) -> dict[str, Any]:
    return apply_cad_action(settings, job_id, [{"type": "translate", "dx_mm": dx_mm, "dy_mm": dy_mm}])


def scale_geometry_tool(settings: Settings, job_id: str, factor: float) -> dict[str, Any]:
    return apply_cad_action(settings, job_id, [{"type": "scale", "factor": factor}])


def render_preview_tool(settings: Settings, job_id: str) -> dict[str, Any]:
    manifest = load_manifest(settings, job_id)
    if manifest is None:
        raise ValueError("Job not found.")
    output_path = settings.storage_dir / "jobs" / job_id / "mcp-preview.png"
    render_dxf_preview(Path(manifest.dxf_path), output_path)
    return {"job_id": job_id, "preview_path": str(output_path), "preview_url": f"/storage/jobs/{job_id}/mcp-preview.png"}

