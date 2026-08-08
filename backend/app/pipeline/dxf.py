from pathlib import Path
from typing import Iterable, Sequence

import ezdxf
from ezdxf import units

Point = tuple[float, float]
Polyline = Sequence[Point]


def write_dxf(
    polylines: Iterable[Polyline],
    output_path: Path,
    *,
    mm_per_pixel: float,
    source_height_px: float,
    layer_name: str,
    color: int,
) -> float:
    doc = ezdxf.new("R2010")
    doc.units = units.MM

    if layer_name not in doc.layers:
        doc.layers.add(layer_name, color=color)

    modelspace = doc.modelspace()
    total_length_mm = 0.0

    for polyline in polylines:
        if len(polyline) < 2:
            continue

        cad_points: list[tuple[float, float]] = []
        previous: tuple[float, float] | None = None
        for x_px, y_px in polyline:
            x_mm = float(x_px) * mm_per_pixel
            y_mm = (source_height_px - float(y_px)) * mm_per_pixel
            point = (x_mm, y_mm)
            cad_points.append(point)
            if previous is not None:
                dx = point[0] - previous[0]
                dy = point[1] - previous[1]
                total_length_mm += (dx * dx + dy * dy) ** 0.5
            previous = point

        modelspace.add_lwpolyline(cad_points, dxfattribs={"layer": layer_name, "color": color})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    return total_length_mm
