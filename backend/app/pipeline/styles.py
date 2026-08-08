from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingStyle:
    id: str
    name: str
    summary: str
    output_mode: str
    layer_name: str
    dxf_color: int
    overlay_bgr: tuple[int, int, int]
    default_sensitivity: float
    default_noise_filter: int
    default_simplify_tolerance: float
    min_length_px: float
    max_dimension_px: int


STYLES: dict[str, ProcessingStyle] = {
    "centerline": ProcessingStyle(
        id="centerline",
        name="Continuous CNC",
        summary="Builds one connected vein network for continuous CNC planning.",
        output_mode="centerline",
        layer_name="VEIN_CENTERLINES",
        dxf_color=3,
        overlay_bgr=(36, 214, 95),
        default_sensitivity=0.64,
        default_noise_filter=2,
        default_simplify_tolerance=1.6,
        min_length_px=22,
        max_dimension_px=1800,
    ),
    "high_detail": ProcessingStyle(
        id="high_detail",
        name="Fine Detail",
        summary="Keeps smaller branches and more of the original vein texture.",
        output_mode="centerline",
        layer_name="VEIN_DETAIL",
        dxf_color=4,
        overlay_bgr=(236, 88, 223),
        default_sensitivity=0.72,
        default_noise_filter=2,
        default_simplify_tolerance=0.9,
        min_length_px=12,
        max_dimension_px=2200,
    ),
    "outline": ProcessingStyle(
        id="outline",
        name="Engrave Outline",
        summary="Closed vein boundaries for pocketing or outlining.",
        output_mode="outline",
        layer_name="VEIN_OUTLINES",
        dxf_color=2,
        overlay_bgr=(48, 168, 255),
        default_sensitivity=0.64,
        default_noise_filter=4,
        default_simplify_tolerance=2.2,
        min_length_px=34,
        max_dimension_px=1800,
    ),
    "color_trace": ProcessingStyle(
        id="color_trace",
        name="Color Trace Overlay",
        summary="Extracts existing green and magenta trace overlays.",
        output_mode="centerline",
        layer_name="VEIN_COLOR_TRACE",
        dxf_color=6,
        overlay_bgr=(46, 226, 238),
        default_sensitivity=0.32,
        default_noise_filter=1,
        default_simplify_tolerance=0.6,
        min_length_px=6,
        max_dimension_px=2400,
    ),
}


def get_style(style_id: str) -> ProcessingStyle:
    try:
        return STYLES[style_id]
    except KeyError as exc:
        valid = ", ".join(sorted(STYLES))
        raise ValueError(f"Unknown style '{style_id}'. Valid styles: {valid}.") from exc
