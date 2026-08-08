from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.config import get_settings
from app.mcp_tools import (
    add_border_tool,
    inspect_dxf_job,
    move_geometry_tool,
    recommend_processing_settings,
    render_preview_tool,
    scale_geometry_tool,
    smooth_tool,
)

mcp = FastMCP("VeinCAD CNC MCP")


@mcp.tool()
def inspect_dxf(job_id: str) -> dict:
    """Inspect DXF layers, entity counts, and processing metrics for a generated job."""
    return inspect_dxf_job(get_settings(), job_id)


@mcp.tool()
def add_border(job_id: str, amount_mm: float = 10.0) -> dict:
    """Add a rectangular border around the generated DXF geometry."""
    return add_border_tool(get_settings(), job_id, amount_mm)


@mcp.tool()
def smooth_geometry(job_id: str, tolerance_mm: float = 2.0) -> dict:
    """Simplify/smooth DXF polylines by tolerance in millimetres."""
    return smooth_tool(get_settings(), job_id, tolerance_mm)


@mcp.tool()
def move_geometry(job_id: str, dx_mm: float = 0.0, dy_mm: float = 0.0) -> dict:
    """Move DXF polyline geometry by millimetres."""
    return move_geometry_tool(get_settings(), job_id, dx_mm, dy_mm)


@mcp.tool()
def scale_geometry(job_id: str, factor: float = 1.0) -> dict:
    """Scale DXF polyline geometry around its center."""
    return scale_geometry_tool(get_settings(), job_id, factor)


@mcp.tool()
def render_preview(job_id: str) -> dict:
    """Render a PNG preview of the generated DXF."""
    return render_preview_tool(get_settings(), job_id)


@mcp.tool()
def recommend_trace_settings(message: str) -> dict:
    """Suggest image extraction settings from a natural-language configuration request."""
    return recommend_processing_settings(message)


if __name__ == "__main__":
    mcp.run()
