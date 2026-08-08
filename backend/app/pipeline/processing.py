from __future__ import annotations

import json
import math
import time
import uuid
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from skimage.graph import route_through_array
from skimage.morphology import skeletonize

from app.config import Settings
from app.models import JobManifest, ProcessMetrics
from app.pipeline.dxf import write_dxf
from app.pipeline.segmentation import Sam2Segmenter
from app.pipeline.styles import ProcessingStyle, get_style

Point = tuple[float, float]
Polyline = list[Point]


@dataclass
class ProcessingRequest:
    style_id: str
    sensitivity: float | None
    noise_filter: int | None
    simplify_tolerance: float | None
    mm_per_pixel: float
    slab_width_mm: float | None
    slab_height_mm: float | None
    original_filename: str


@dataclass
class WorkArea:
    x: int
    y: int
    width: int
    height: int


NEIGHBOUR_OFFSETS = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)

USER_STYLE_IDS = {"centerline", "high_detail"}


def process_upload(
    *,
    image_bytes: bytes,
    request: ProcessingRequest,
    settings: Settings,
    segmenter: Sam2Segmenter | None = None,
) -> JobManifest:
    started = time.perf_counter()
    style_id = request.style_id if request.style_id in USER_STYLE_IDS else "centerline"
    style = get_style(style_id)
    image = _decode_image(image_bytes)
    processed_image, resize_ratio = _resize_for_processing(image, style.max_dimension_px)
    work_area = _detect_work_area(processed_image)
    roi = processed_image[
        work_area.y : work_area.y + work_area.height,
        work_area.x : work_area.x + work_area.width,
    ]

    sensitivity = _clamp(
        request.sensitivity if request.sensitivity is not None else style.default_sensitivity,
        0.05,
        0.95,
    )
    noise_filter = int(
        _clamp(
            float(request.noise_filter if request.noise_filter is not None else style.default_noise_filter),
            0,
            10,
        )
    )
    simplify_tolerance = _clamp(
        request.simplify_tolerance
        if request.simplify_tolerance is not None
        else style.default_simplify_tolerance,
        0.0,
        8.0,
    )
    source_width_px = work_area.width / resize_ratio
    source_height_px = work_area.height / resize_ratio
    mm_per_pixel, scale_confirmed = _resolve_scale(
        request.mm_per_pixel,
        request.slab_width_mm,
        request.slab_height_mm,
        source_width_px,
        source_height_px,
    )

    sam_result = segmenter.segment(roi) if segmenter else None
    mask = _extract_vein_mask(roi, style, sensitivity, noise_filter, sam_result.mask if sam_result else None)

    if style.output_mode == "outline":
        polylines = _contours_to_polylines(mask, style.min_length_px, simplify_tolerance)
    else:
        skeleton = _skeletonize_mask(mask)
        polylines = _skeleton_graph_to_polylines(skeleton, simplify_tolerance)
        polylines = _prune_skeleton_segments(polylines, style.min_length_px)
        if style.id == "centerline":
            polylines = [_smooth_polyline(polyline, passes=1) for polyline in polylines]
            polylines = [
                polyline for polyline in polylines if not _is_axis_aligned_reflection(polyline)
            ]
            confidence = _vein_confidence_map(roi)
            polylines = _connect_supported_gaps(
                polylines,
                confidence,
                max_gap_px=24.0,
            )
            polylines = _consolidate_small_components(
                polylines,
                confidence,
                min_component_length_px=110.0,
                discard_length_px=48.0,
                max_gap_px=68.0,
            )
            polylines = _connect_component_network(polylines, confidence)
            for _ in range(4):
                endpoint_count = _internal_endpoint_count(
                    polylines,
                    confidence.shape,
                    border_margin_px=10,
                )
                if endpoint_count == 0:
                    break
                closed_polylines = _close_internal_endpoints(
                    polylines,
                    confidence,
                    border_margin_px=10,
                    max_gap_px=132.0,
                )
                remaining = _internal_endpoint_count(
                    closed_polylines,
                    confidence.shape,
                    border_margin_px=10,
                )
                polylines = closed_polylines
                if remaining >= endpoint_count:
                    break
            polylines = _prune_internal_terminal_paths(
                polylines,
                confidence.shape,
                border_margin_px=10,
                max_terminal_length_px=85.0,
            )
            polylines = _connect_component_network(polylines, confidence)
            for _ in range(5):
                endpoint_count = _internal_endpoint_count(
                    polylines,
                    confidence.shape,
                    border_margin_px=10,
                )
                if endpoint_count == 0:
                    break
                closed_polylines = _close_internal_endpoints(
                    polylines,
                    confidence,
                    border_margin_px=10,
                    max_gap_px=220.0,
                )
                remaining = _internal_endpoint_count(
                    closed_polylines,
                    confidence.shape,
                    border_margin_px=10,
                )
                polylines = closed_polylines
                if remaining >= endpoint_count:
                    break
        elif style.id == "high_detail":
            polylines = [_smooth_polyline(polyline, passes=1) for polyline in polylines]
            polylines = [
                polyline for polyline in polylines if not _is_axis_aligned_reflection(polyline)
            ]

    preview_polylines = polylines
    toolpath_mask = _rasterize_polylines(mask.shape, preview_polylines)
    polylines = _scale_polylines_to_source(preview_polylines, resize_ratio)
    job_id = uuid.uuid4().hex
    job_dir = settings.storage_dir / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / _safe_input_name(request.original_filename)
    input_path.write_bytes(image_bytes)

    preview_path = job_dir / "preview.png"
    mask_path = job_dir / "mask.png"
    dxf_path = job_dir / "veincad-output.dxf"

    _write_preview(processed_image, work_area, toolpath_mask, preview_polylines, style, preview_path)
    cv2.imwrite(str(mask_path), toolpath_mask)
    total_length_mm = write_dxf(
        polylines,
        dxf_path,
        mm_per_pixel=mm_per_pixel,
        source_height_px=source_height_px,
        layer_name=style.layer_name,
        color=style.dxf_color,
    )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    metrics = ProcessMetrics(
        width_px=int(source_width_px),
        height_px=int(source_height_px),
        work_area=[
            int(work_area.x / resize_ratio),
            int(work_area.y / resize_ratio),
            int(source_width_px),
            int(source_height_px),
        ],
        mm_per_pixel=round(mm_per_pixel, 6),
        scale_confirmed=scale_confirmed,
        line_count=len(polylines),
        total_length_mm=round(total_length_mm, 2),
        used_sam2=bool(sam_result),
        processing_ms=elapsed_ms,
    )

    manifest = JobManifest(
        job_id=job_id,
        style_id=style.id,
        original_filename=request.original_filename,
        preview_path=str(preview_path),
        mask_path=str(mask_path),
        dxf_path=str(dxf_path),
        metrics=metrics,
    )
    (job_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def load_manifest(settings: Settings, job_id: str) -> JobManifest | None:
    manifest_path = settings.storage_dir / "jobs" / job_id / "manifest.json"
    if not manifest_path.exists():
        return None
    return JobManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))


def _decode_image(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The uploaded file is not a readable image.")
    return image


def _resize_for_processing(image: np.ndarray, max_dimension: int) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    largest = max(width, height)
    if largest <= max_dimension:
        return image, 1.0

    ratio = max_dimension / float(largest)
    resized = cv2.resize(image, (int(width * ratio), int(height * ratio)), interpolation=cv2.INTER_AREA)
    return resized, ratio


def _detect_work_area(image: np.ndarray) -> WorkArea:
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    broad_projection_mask = np.where((saturation < 130) & (value > 115), 255, 0).astype(np.uint8)
    strict_projection_mask = np.where((saturation < 90) & (value > 138), 255, 0).astype(np.uint8)
    broad_area = _projection_work_area(broad_projection_mask)
    strict_area = _projection_work_area(strict_projection_mask)
    if broad_area is not None and strict_area is not None:
        preserves_width = strict_area.width >= broad_area.width * 0.9
        removes_excess_height = strict_area.height < broad_area.height * 0.9
        return strict_area if preserves_width and removes_excess_height else broad_area
    if strict_area is not None:
        return strict_area
    if broad_area is not None:
        return broad_area

    light_mask = np.where((saturation < 90) & (value > 138), 255, 0).astype(np.uint8)
    kernel_size = max(9, int(min(width, height) * 0.025))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    light_mask = cv2.morphologyEx(light_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(light_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return WorkArea(0, 0, width, height)

    image_area = width * height
    candidates: list[tuple[float, tuple[int, int, int, int]]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.12:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        bbox_ratio = (w * h) / image_area
        if w < width * 0.2 or h < height * 0.2:
            continue
        candidates.append((bbox_ratio, (x, y, w, h)))

    if not candidates:
        return WorkArea(0, 0, width, height)

    _, (x, y, w, h) = max(candidates, key=lambda item: item[0])
    if w * h > image_area * 0.92:
        return WorkArea(0, 0, width, height)

    padding = max(2, int(min(width, height) * 0.006))
    x0 = max(0, x + padding)
    y0 = max(0, y + padding)
    x1 = min(width, x + w - padding)
    y1 = min(height, y + h - padding)
    return WorkArea(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def _projection_work_area(light_mask: np.ndarray) -> WorkArea | None:
    height, width = light_mask.shape[:2]
    normalized = (light_mask > 0).astype(np.float32)
    row_fraction = _smooth_projection(normalized.mean(axis=1), max(5, int(height * 0.012)))

    row_band = _find_projection_band(
        row_fraction,
        thresholds=(0.65, 0.55, 0.45, 0.35),
        min_fraction=0.2,
    )
    if row_band is None:
        return None

    y0, y1 = row_band
    row_scoped_mask = normalized[y0:y1, :]
    col_fraction = _smooth_projection(row_scoped_mask.mean(axis=0), max(5, int(width * 0.01)))
    col_band = _find_projection_band(
        col_fraction,
        thresholds=(0.35, 0.45, 0.55, 0.25),
        min_fraction=0.35,
        allow_full_span=True,
    )
    if col_band is None:
        return None

    x0, x1 = col_band
    candidate_width = x1 - x0
    candidate_height = y1 - y0
    area_ratio = (candidate_width * candidate_height) / float(width * height)

    if area_ratio < 0.12 or area_ratio > 0.92:
        return None
    if candidate_width < width * 0.35 or candidate_height < height * 0.2:
        return None

    padding = max(2, int(min(width, height) * 0.006))
    x0 = min(max(0, x0 + padding), width - 1)
    y0 = min(max(0, y0 + padding), height - 1)
    x1 = max(min(width, x1 - padding), x0 + 1)
    y1 = max(min(height, y1 - padding), y0 + 1)

    return WorkArea(x0, y0, x1 - x0, y1 - y0)


def _smooth_projection(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    if window % 2 == 0:
        window += 1
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(values, kernel, mode="same")


def _find_projection_band(
    values: np.ndarray,
    *,
    thresholds: tuple[float, ...],
    min_fraction: float,
    allow_full_span: bool = False,
) -> tuple[int, int] | None:
    dimension = len(values)
    for threshold in thresholds:
        bands: list[tuple[int, int]] = []
        start: int | None = None
        for index, value in enumerate(values):
            if value > threshold and start is None:
                start = index
            at_end = index == dimension - 1
            if start is not None and (value <= threshold or at_end):
                end = index if value <= threshold else index + 1
                bands.append((start, end))
                start = None

        if not bands:
            continue

        best = max(bands, key=lambda band: band[1] - band[0])
        length = best[1] - best[0]
        if length < dimension * min_fraction:
            continue
        if (
            not allow_full_span
            and length > dimension * 0.92
            and best[0] < dimension * 0.04
            and best[1] > dimension * 0.96
        ):
            continue
        return best

    return None


def _extract_vein_mask(
    image: np.ndarray,
    style: ProcessingStyle,
    sensitivity: float,
    noise_filter: int,
    sam_mask: np.ndarray | None,
) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    clahe = cv2.createCLAHE(clipLimit=2.0 + sensitivity, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blur = cv2.bilateralFilter(enhanced, d=7, sigmaColor=42, sigmaSpace=42)

    vein_width = max(7, int(min(image.shape[:2]) * (0.012 + sensitivity * 0.012)))
    if vein_width % 2 == 0:
        vein_width += 1
    blackhat_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (vein_width, vein_width))
    blackhat = cv2.morphologyEx(blur, cv2.MORPH_BLACKHAT, blackhat_kernel)

    nonzero = blackhat[blackhat > 0]
    if nonzero.size:
        threshold = max(4, float(np.percentile(nonzero, 95 - sensitivity * 14)))
    else:
        threshold = 255
    dark_mask = np.where(blackhat >= threshold, 255, 0).astype(np.uint8)

    block_size = max(15, int(min(image.shape[:2]) * 0.06))
    if block_size % 2 == 0:
        block_size += 1
    adaptive = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        7 + int((1.0 - sensitivity) * 8),
    )

    median = float(np.median(blur))
    lower = int(max(0, median * (0.58 - sensitivity * 0.32)))
    upper = int(min(255, median * (1.22 + sensitivity * 0.55)))
    edges = cv2.Canny(blur, lower, max(lower + 20, upper))
    edge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edges = cv2.dilate(edges, edge_kernel, iterations=1)
    edge_support = cv2.dilate(
        edges,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        iterations=1,
    )

    colored_line_mask = np.where(
        (saturation > max(35, int(92 - sensitivity * 45))) & (value > 45),
        255,
        0,
    ).astype(np.uint8)

    if style.id == "color_trace":
        return _clean_binary_mask(colored_line_mask, noise_filter)

    structural_support = cv2.bitwise_and(adaptive, edge_support)
    mask = cv2.bitwise_or(dark_mask, structural_support)
    mask = cv2.bitwise_or(mask, colored_line_mask)

    if sam_mask is not None:
        sam_mask = cv2.resize(sam_mask, (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_NEAREST)
        mask = cv2.bitwise_or(mask, cv2.bitwise_and(mask, sam_mask))

    mask = _clean_binary_mask(mask, noise_filter)
    return mask


def _clean_binary_mask(mask: np.ndarray, noise_filter: int) -> np.ndarray:
    close_size = max(2, noise_filter + 1)
    open_size = max(1, noise_filter // 2)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_size, open_size))

    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=1)
    if open_size > 1:
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, open_kernel, iterations=1)
    cleaned = _bridge_line_gaps(cleaned, max_gap_px=max(5, noise_filter * 2 + 3))

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    min_area = max(6, int((noise_filter + 1) * 5))
    output = np.zeros_like(cleaned)
    for label in range(1, component_count):
        area = stats[label, cv2.CC_STAT_AREA]
        if area >= min_area:
            output[labels == label] = 255

    border_margin = max(2, noise_filter + 1)
    output[:border_margin, :] = 0
    output[-border_margin:, :] = 0
    output[:, :border_margin] = 0
    output[:, -border_margin:] = 0
    return output


def _bridge_line_gaps(mask: np.ndarray, max_gap_px: int) -> np.ndarray:
    if max_gap_px < 3:
        return mask

    kernel_size = int(max_gap_px)
    if kernel_size % 2 == 0:
        kernel_size += 1

    kernels = [
        cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, 1)),
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_size)),
        np.eye(kernel_size, dtype=np.uint8),
        np.fliplr(np.eye(kernel_size, dtype=np.uint8)),
    ]

    bridged = mask.copy()
    for kernel in kernels:
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        bridged = cv2.bitwise_or(bridged, closed)

    return bridged


def _skeletonize_mask(mask: np.ndarray) -> np.ndarray:
    skeleton = skeletonize(mask > 0)
    return (skeleton.astype(np.uint8)) * 255


def _skeleton_to_polylines(
    skeleton: np.ndarray,
    min_length_px: float,
    simplify_tolerance: float,
) -> list[Polyline]:
    pixels = {(int(x), int(y)) for y, x in zip(*np.nonzero(skeleton))}
    if not pixels:
        return []

    neighbour_cache = {pixel: _pixel_neighbours(pixel, pixels) for pixel in pixels}
    nodes = [pixel for pixel, neighbours in neighbour_cache.items() if len(neighbours) != 2]
    visited_edges: set[tuple[Point, Point]] = set()
    polylines: list[Polyline] = []

    for node in nodes:
        for neighbour in neighbour_cache[node]:
            edge = _edge_key(node, neighbour)
            if edge in visited_edges:
                continue
            path = _walk_skeleton_path(node, neighbour, neighbour_cache, visited_edges)
            _append_polyline(polylines, path, min_length_px, simplify_tolerance)

    for pixel in pixels:
        for neighbour in neighbour_cache[pixel]:
            edge = _edge_key(pixel, neighbour)
            if edge in visited_edges:
                continue
            path = _walk_skeleton_path(pixel, neighbour, neighbour_cache, visited_edges)
            _append_polyline(polylines, path, min_length_px, simplify_tolerance)

    return polylines


def _skeleton_graph_to_polylines(
    skeleton: np.ndarray,
    simplify_tolerance: float,
) -> list[Polyline]:
    """Collapse junction pixel clusters before tracing graph edges."""
    binary = (skeleton > 0).astype(np.uint8)
    if not np.any(binary):
        return []

    neighbour_kernel = np.ones((3, 3), dtype=np.uint8)
    neighbour_count = cv2.filter2D(
        binary,
        cv2.CV_16S,
        neighbour_kernel,
        borderType=cv2.BORDER_CONSTANT,
    ) - binary
    junction_mask = np.where((binary > 0) & (neighbour_count > 2), 1, 0).astype(np.uint8)
    junction_mask = cv2.bitwise_and(
        cv2.dilate(junction_mask, neighbour_kernel, iterations=1),
        binary,
    )

    junction_count, junction_labels, _, junction_centroids = cv2.connectedComponentsWithStats(
        junction_mask,
        connectivity=8,
    )
    branch_mask = cv2.bitwise_and(binary, cv2.bitwise_not(junction_mask)) * 255
    polylines = _skeleton_to_polylines(branch_mask, 1.0, simplify_tolerance)

    if junction_count <= 1:
        return polylines

    return [
        _attach_path_to_junction_nodes(path, junction_labels, junction_centroids)
        for path in polylines
    ]


def _attach_path_to_junction_nodes(
    path: Polyline,
    junction_labels: np.ndarray,
    junction_centroids: np.ndarray,
) -> Polyline:
    connected = list(path)
    height, width = junction_labels.shape[:2]
    search_radius = 4

    for at_start in (True, False):
        endpoint = connected[0] if at_start else connected[-1]
        x = int(round(endpoint[0]))
        y = int(round(endpoint[1]))
        x0 = max(0, x - search_radius)
        x1 = min(width, x + search_radius + 1)
        y0 = max(0, y - search_radius)
        y1 = min(height, y + search_radius + 1)
        nearby_labels = np.unique(junction_labels[y0:y1, x0:x1])
        nearby_labels = nearby_labels[nearby_labels > 0]
        if not nearby_labels.size:
            continue

        label = min(
            (int(item) for item in nearby_labels),
            key=lambda item: math.dist(
                endpoint,
                (
                    float(junction_centroids[item][0]),
                    float(junction_centroids[item][1]),
                ),
            ),
        )
        node = (
            float(junction_centroids[label][0]),
            float(junction_centroids[label][1]),
        )
        if at_start:
            connected.insert(0, node)
        else:
            connected.append(node)

    return connected


def _prune_skeleton_segments(
    polylines: list[Polyline],
    min_length_px: float,
) -> list[Polyline]:
    """Remove noise without deleting short edges that hold junctions together."""
    working = [path for path in polylines if len(path) >= 2]
    terminal_min = max(4.0, min_length_px * 0.65)
    isolated_min = max(8.0, min_length_px * 1.5)

    for _ in range(4):
        endpoint_counts = Counter(
            _point_key(endpoint)
            for path in working
            for endpoint in (path[0], path[-1])
        )
        kept: list[Polyline] = []
        removed = False

        for path in working:
            length = _polyline_length(path)
            start_key = _point_key(path[0])
            end_key = _point_key(path[-1])
            start_shared = endpoint_counts[start_key] > 1
            end_shared = endpoint_counts[end_key] > 1
            closed = start_key == end_key

            if closed:
                keep = length >= isolated_min
            elif start_shared and end_shared:
                keep = length >= 1.0
            elif start_shared or end_shared:
                keep = length >= terminal_min
            else:
                keep = length >= isolated_min

            if keep:
                kept.append(path)
            else:
                removed = True

        working = kept
        if not removed:
            break

    return working


def _point_key(point: Point) -> tuple[int, int]:
    return (int(round(point[0])), int(round(point[1])))


def _connection_gap_px(style: ProcessingStyle, sensitivity: float, noise_filter: int) -> float:
    gap = 12.0 + noise_filter * 4.0 + sensitivity * 12.0
    if style.id == "high_detail":
        gap *= 0.75
    elif style.id == "color_trace":
        gap *= 0.65
    return _clamp(gap, 8.0, 42.0)


def _stitch_polylines(
    polylines: list[Polyline],
    *,
    max_gap_px: float,
    simplify_tolerance: float,
) -> list[Polyline]:
    working = [path for path in polylines if len(path) >= 2]
    if len(working) < 2:
        return working

    max_iterations = max(0, len(working) - 1)
    for _ in range(max_iterations):
        candidate = _best_stitch_candidate(working, max_gap_px)
        if candidate is None:
            break
        first_index, first_at_start, second_index, second_at_start = candidate
        merged = _merge_polylines(
            working[first_index],
            first_at_start=first_at_start,
            second=working[second_index],
            second_at_start=second_at_start,
        )
        working[first_index] = _simplify_polyline(merged, simplify_tolerance)
        del working[second_index]

    return working


def _best_stitch_candidate(
    polylines: list[Polyline],
    max_gap_px: float,
) -> tuple[int, bool, int, bool] | None:
    endpoints: list[tuple[int, bool, Point, Point]] = []
    for index, path in enumerate(polylines):
        endpoints.append((index, True, path[0], _endpoint_direction(path, at_start=True)))
        endpoints.append((index, False, path[-1], _endpoint_direction(path, at_start=False)))

    if len(endpoints) < 2:
        return None

    cell_size = max(max_gap_px, 1.0)
    buckets: dict[tuple[int, int], list[int]] = {}
    for endpoint_index, (_, _, point, _) in enumerate(endpoints):
        cell = (int(point[0] // cell_size), int(point[1] // cell_size))
        buckets.setdefault(cell, []).append(endpoint_index)

    best: tuple[float, tuple[int, bool, int, bool]] | None = None
    for endpoint_index, endpoint in enumerate(endpoints):
        first_polyline, first_at_start, first_point, first_direction = endpoint
        cell = (int(first_point[0] // cell_size), int(first_point[1] // cell_size))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other_index in buckets.get((cell[0] + dx, cell[1] + dy), []):
                    if other_index <= endpoint_index:
                        continue
                    second_polyline, second_at_start, second_point, second_direction = endpoints[other_index]
                    if first_polyline == second_polyline:
                        continue
                    distance = math.dist(first_point, second_point)
                    if distance > max_gap_px:
                        continue
                    if not _endpoints_align(first_point, first_direction, second_point, second_direction):
                        continue

                    score = distance
                    candidate = (first_polyline, first_at_start, second_polyline, second_at_start)
                    if best is None or score < best[0]:
                        best = (score, candidate)

    if best is None:
        return None

    first_index, first_at_start, second_index, second_at_start = best[1]
    if first_index > second_index:
        return second_index, second_at_start, first_index, first_at_start
    return first_index, first_at_start, second_index, second_at_start


def _endpoint_direction(path: Polyline, *, at_start: bool) -> Point:
    sample_count = min(6, len(path) - 1)
    if sample_count <= 0:
        return (0.0, 0.0)
    endpoint = path[0] if at_start else path[-1]
    neighbour = path[sample_count] if at_start else path[-1 - sample_count]
    direction = (endpoint[0] - neighbour[0], endpoint[1] - neighbour[1])
    length = math.hypot(direction[0], direction[1])
    if length == 0:
        return (0.0, 0.0)
    return (direction[0] / length, direction[1] / length)


def _endpoints_align(
    first_point: Point,
    first_direction: Point,
    second_point: Point,
    second_direction: Point,
) -> bool:
    bridge = (second_point[0] - first_point[0], second_point[1] - first_point[1])
    bridge_length = math.hypot(bridge[0], bridge[1])
    if bridge_length <= 2.0:
        return True

    bridge_unit = (bridge[0] / bridge_length, bridge[1] / bridge_length)
    first_alignment = first_direction[0] * bridge_unit[0] + first_direction[1] * bridge_unit[1]
    second_alignment = second_direction[0] * -bridge_unit[0] + second_direction[1] * -bridge_unit[1]
    return first_alignment >= -0.15 and second_alignment >= -0.15


def _merge_polylines(
    first: Polyline,
    *,
    first_at_start: bool,
    second: Polyline,
    second_at_start: bool,
) -> Polyline:
    first_points = list(reversed(first)) if first_at_start else list(first)
    second_points = list(second) if second_at_start else list(reversed(second))
    return first_points + second_points


def _attach_dangling_endpoints(
    polylines: list[Polyline],
    *,
    max_gap_px: float,
) -> list[Polyline]:
    working = [list(path) for path in polylines if len(path) >= 2]
    if len(working) < 2 or max_gap_px <= 0:
        return working

    for path_index, path in enumerate(working):
        for at_start in (True, False):
            endpoint = path[0] if at_start else path[-1]
            direction = _endpoint_direction(path, at_start=at_start)
            best: tuple[float, Point] | None = None

            for target_index, target in enumerate(working):
                if target_index == path_index:
                    continue
                for segment_index in range(len(target) - 1):
                    nearest = _nearest_point_on_segment(
                        endpoint,
                        target[segment_index],
                        target[segment_index + 1],
                    )
                    distance = math.dist(endpoint, nearest)
                    if distance <= 2.0 or distance > max_gap_px:
                        continue
                    bridge = (
                        (nearest[0] - endpoint[0]) / distance,
                        (nearest[1] - endpoint[1]) / distance,
                    )
                    alignment = direction[0] * bridge[0] + direction[1] * bridge[1]
                    if direction != (0.0, 0.0) and alignment < 0.15:
                        continue
                    if best is None or distance < best[0]:
                        best = (distance, nearest)

            if best is None:
                continue
            if at_start:
                path.insert(0, best[1])
            else:
                path.append(best[1])

    return working


def _vein_confidence_map(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    smoothed = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=1.0)
    local_background = cv2.GaussianBlur(smoothed, (0, 0), sigmaX=5.0)
    broad_background = cv2.GaussianBlur(smoothed, (0, 0), sigmaX=11.0)
    response = np.maximum(
        local_background.astype(np.float32) - smoothed.astype(np.float32),
        broad_background.astype(np.float32) - smoothed.astype(np.float32),
    )
    positive = response[response > 0]
    if not positive.size:
        return np.zeros_like(response, dtype=np.float32)

    low = float(np.percentile(positive, 55))
    high = float(np.percentile(positive, 99))
    if high <= low:
        return np.zeros_like(response, dtype=np.float32)
    return np.clip((response - low) / (high - low), 0.0, 1.0).astype(np.float32)


def _connect_supported_gaps(
    polylines: list[Polyline],
    confidence: np.ndarray,
    *,
    max_gap_px: float,
) -> list[Polyline]:
    working = [list(path) for path in polylines if len(path) >= 2]
    if len(working) < 2 or max_gap_px <= 0:
        return working

    parents = list(range(len(working)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    endpoint_owners: dict[tuple[int, int], int] = {}
    endpoint_counts: Counter[tuple[int, int]] = Counter()
    for path_index, path in enumerate(working):
        for endpoint in (path[0], path[-1]):
            key = _point_key(endpoint)
            endpoint_counts[key] += 1
            owner = endpoint_owners.get(key)
            if owner is None:
                endpoint_owners[key] = path_index
            else:
                union(owner, path_index)

    endpoints: list[tuple[int, Point, Point]] = []
    for path_index, path in enumerate(working):
        for at_start in (True, False):
            point = path[0] if at_start else path[-1]
            if endpoint_counts[_point_key(point)] != 1:
                continue
            endpoints.append(
                (
                    path_index,
                    point,
                    _endpoint_direction(path, at_start=at_start),
                )
            )

    candidates: list[tuple[float, int, int, Polyline]] = []
    for first_index, (first_path, first_point, first_direction) in enumerate(endpoints):
        for second_path, second_point, second_direction in endpoints[first_index + 1 :]:
            if first_path == second_path or find(first_path) == find(second_path):
                continue
            distance = math.dist(first_point, second_point)
            if distance <= 2.0 or distance > max_gap_px:
                continue
            if not _endpoints_align(
                first_point,
                first_direction,
                second_point,
                second_direction,
            ):
                continue

            supported = _supported_gap_route(
                confidence,
                first_point,
                second_point,
                max_gap_px=max_gap_px,
            )
            if supported is None:
                continue
            route, support_fraction, length_ratio = supported
            score = (
                (1.0 - support_fraction) * 4.0
                + length_ratio
                + distance / max_gap_px
            )
            candidates.append((score, first_path, second_path, route))

    max_connectors = max(1, min(24, len(working) // 12))
    added = 0
    for _, first_path, second_path, route in sorted(candidates, key=lambda item: item[0]):
        if find(first_path) == find(second_path):
            continue
        working.append(route)
        union(first_path, second_path)
        added += 1
        if added >= max_connectors:
            break

    return working


def _supported_gap_route(
    confidence: np.ndarray,
    start: Point,
    end: Point,
    *,
    max_gap_px: float,
    min_support_fraction: float = 0.68,
    min_mean_confidence: float = 0.24,
    max_unsupported_run: int = 5,
    max_length_ratio: float = 1.55,
) -> tuple[Polyline, float, float] | None:
    distance = math.dist(start, end)
    if distance <= 2.0 or distance > max_gap_px:
        return None

    height, width = confidence.shape[:2]
    margin = 5
    x0 = max(0, int(math.floor(min(start[0], end[0]))) - margin)
    y0 = max(0, int(math.floor(min(start[1], end[1]))) - margin)
    x1 = min(width, int(math.ceil(max(start[0], end[0]))) + margin + 1)
    y1 = min(height, int(math.ceil(max(start[1], end[1]))) + margin + 1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None

    local_confidence = confidence[y0:y1, x0:x1]
    cost = 1.0 + (1.0 - local_confidence) * 8.0
    local_start = (
        int(round(start[1])) - y0,
        int(round(start[0])) - x0,
    )
    local_end = (
        int(round(end[1])) - y0,
        int(round(end[0])) - x0,
    )
    try:
        indices, _ = route_through_array(
            cost,
            local_start,
            local_end,
            fully_connected=True,
            geometric=True,
        )
    except (IndexError, ValueError):
        return None
    if len(indices) < 2:
        return None

    values = np.array(
        [local_confidence[row, column] for row, column in indices],
        dtype=np.float32,
    )
    interior = values[2:-2] if len(values) > 5 else values
    supported = interior >= 0.16
    support_fraction = float(np.mean(supported)) if supported.size else 0.0
    if (
        support_fraction < min_support_fraction
        or float(np.mean(interior)) < min_mean_confidence
    ):
        return None

    longest_unsupported = 0
    current_unsupported = 0
    for is_supported in supported:
        if is_supported:
            current_unsupported = 0
        else:
            current_unsupported += 1
            longest_unsupported = max(longest_unsupported, current_unsupported)
    if longest_unsupported > max_unsupported_run:
        return None

    route: Polyline = [
        (float(column + x0), float(row + y0))
        for row, column in indices
    ]
    route[0] = start
    route[-1] = end
    route_length = _polyline_length(route)
    length_ratio = route_length / distance
    if length_ratio > max_length_ratio:
        return None

    return _simplify_polyline(route, 0.8), support_fraction, length_ratio


def _consolidate_small_components(
    polylines: list[Polyline],
    confidence: np.ndarray,
    *,
    min_component_length_px: float,
    discard_length_px: float,
    max_gap_px: float,
) -> list[Polyline]:
    working = [list(path) for path in polylines if len(path) >= 2]
    groups = _polyline_component_groups(working)
    if len(groups) < 2:
        return working

    group_lengths = {
        root: sum(_polyline_length(working[index]) for index in indices)
        for root, indices in groups.items()
    }
    target_roots = {
        root
        for root, length in group_lengths.items()
        if length >= min_component_length_px
    }
    if not target_roots:
        return working

    keep = [True] * len(working)
    connectors: list[Polyline] = []
    small_groups = sorted(
        (
            (root, indices)
            for root, indices in groups.items()
            if group_lengths[root] < min_component_length_px
        ),
        key=lambda item: group_lengths[item[0]],
        reverse=True,
    )

    for root, indices in small_groups:
        candidates = _component_connection_candidates(
            working,
            source_indices=indices,
            target_indices=[
                index
                for target_root in target_roots
                for index in groups[target_root]
            ],
            max_gap_px=max_gap_px,
        )
        connector: Polyline | None = None
        for _, source_point, target_point in candidates[:12]:
            supported = _supported_gap_route(
                confidence,
                source_point,
                target_point,
                max_gap_px=max_gap_px,
                min_support_fraction=0.46,
                min_mean_confidence=0.17,
                max_unsupported_run=11,
                max_length_ratio=1.75,
            )
            if supported is not None:
                connector = supported[0]
                break

        if connector is not None:
            connectors.append(connector)
            target_roots.add(root)
        elif group_lengths[root] < discard_length_px:
            for index in indices:
                keep[index] = False

    return [
        path for index, path in enumerate(working) if keep[index]
    ] + connectors


def _polyline_component_groups(polylines: list[Polyline]) -> dict[int, list[int]]:
    parents = list(range(len(polylines)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    endpoint_owner: dict[tuple[int, int], int] = {}
    for index, path in enumerate(polylines):
        for endpoint in (path[0], path[-1]):
            key = _point_key(endpoint)
            owner = endpoint_owner.get(key)
            if owner is None:
                endpoint_owner[key] = index
                continue
            first_root = find(owner)
            second_root = find(index)
            if first_root != second_root:
                parents[second_root] = first_root

    groups: dict[int, list[int]] = {}
    for index in range(len(polylines)):
        groups.setdefault(find(index), []).append(index)
    return groups


def _component_connection_candidates(
    polylines: list[Polyline],
    *,
    source_indices: list[int],
    target_indices: list[int],
    max_gap_px: float,
) -> list[tuple[float, Point, Point]]:
    source_points: list[Point] = []
    for index in source_indices:
        path = polylines[index]
        stride = max(1, len(path) // 12)
        source_points.extend(path[::stride])
        source_points.extend((path[0], path[-1]))

    candidates: dict[tuple[int, int, int, int], tuple[float, Point, Point]] = {}
    for source in source_points:
        for target_index in target_indices:
            target = polylines[target_index]
            for segment_index in range(len(target) - 1):
                nearest = _nearest_point_on_segment(
                    source,
                    target[segment_index],
                    target[segment_index + 1],
                )
                distance = math.dist(source, nearest)
                if distance <= 2.0 or distance > max_gap_px:
                    continue
                key = (
                    int(round(source[0])),
                    int(round(source[1])),
                    int(round(nearest[0])),
                    int(round(nearest[1])),
                )
                candidate = (distance, source, nearest)
                existing = candidates.get(key)
                if existing is None or distance < existing[0]:
                    candidates[key] = candidate

    return sorted(candidates.values(), key=lambda item: item[0])


def _connect_component_network(
    polylines: list[Polyline],
    confidence: np.ndarray,
) -> list[Polyline]:
    working = [list(path) for path in polylines if len(path) >= 2]
    if len(working) < 2:
        return working

    raster = _rasterize_polylines(confidence.shape, working)
    component_count, labels = cv2.connectedComponents((raster > 0).astype(np.uint8), connectivity=8)
    if component_count <= 2:
        return working

    component_points: dict[int, list[Point]] = {}
    for path in working:
        label = _path_component_label(path, labels)
        if label <= 0:
            continue
        points = component_points.setdefault(label, [])
        for start, end in zip(path, path[1:]):
            distance = math.dist(start, end)
            samples = max(1, int(math.ceil(distance / 6.0)))
            for step in range(samples):
                ratio = step / samples
                points.append(
                    (
                        start[0] + (end[0] - start[0]) * ratio,
                        start[1] + (end[1] - start[1]) * ratio,
                    )
                )
        points.append(path[-1])

    component_labels = sorted(component_points)
    if len(component_labels) < 2:
        return working

    sampled_points: dict[int, np.ndarray] = {}
    for label, points in component_points.items():
        stride = max(1, len(points) // 320)
        sampled_points[label] = np.asarray(points[::stride], dtype=np.float32)

    edges: list[tuple[float, int, int, Point, Point]] = []
    for first_position, first_label in enumerate(component_labels):
        first_points = sampled_points[first_label]
        for second_label in component_labels[first_position + 1 :]:
            second_points = sampled_points[second_label]
            differences = first_points[:, None, :] - second_points[None, :, :]
            distances_squared = np.sum(differences * differences, axis=2)
            flat_index = int(np.argmin(distances_squared))
            first_index, second_index = np.unravel_index(flat_index, distances_squared.shape)
            first_point = tuple(float(value) for value in first_points[first_index])
            second_point = tuple(float(value) for value in second_points[second_index])
            distance = math.sqrt(float(distances_squared[first_index, second_index]))
            edges.append(
                (
                    distance,
                    first_label,
                    second_label,
                    first_point,
                    second_point,
                )
            )

    parents = {label: label for label in component_labels}

    def find(label: int) -> int:
        while parents[label] != label:
            parents[label] = parents[parents[label]]
            label = parents[label]
        return label

    connectors: list[Polyline] = []
    for distance, first_label, second_label, first_point, second_point in sorted(
        edges,
        key=lambda item: item[0],
    ):
        first_root = find(first_label)
        second_root = find(second_label)
        if first_root == second_root:
            continue

        supported = _supported_gap_route(
            confidence,
            first_point,
            second_point,
            max_gap_px=max(3.0, distance + 1.0),
            min_support_fraction=0.0,
            min_mean_confidence=0.0,
            max_unsupported_run=max(confidence.shape),
            max_length_ratio=2.5,
        )
        connector = supported[0] if supported is not None else [first_point, second_point]
        connectors.append(connector)
        parents[second_root] = first_root
        if len(connectors) >= len(component_labels) - 1:
            break

    return working + connectors


def _path_component_label(path: Polyline, labels: np.ndarray) -> int:
    height, width = labels.shape[:2]
    counts: Counter[int] = Counter()
    for point in path:
        x = int(round(point[0]))
        y = int(round(point[1]))
        if 0 <= x < width and 0 <= y < height:
            label = int(labels[y, x])
            if label > 0:
                counts[label] += 1
    return counts.most_common(1)[0][0] if counts else 0


def _close_internal_endpoints(
    polylines: list[Polyline],
    confidence: np.ndarray,
    *,
    border_margin_px: int,
    max_gap_px: float,
) -> list[Polyline]:
    working = [list(path) for path in polylines if len(path) >= 2]
    if len(working) < 2:
        return working

    raster = _rasterize_polylines(confidence.shape, working)
    skeleton = _skeletonize_mask(raster)
    binary = (skeleton > 0).astype(np.uint8)
    neighbour_count = cv2.filter2D(
        binary,
        cv2.CV_16S,
        np.ones((3, 3), dtype=np.uint8),
        borderType=cv2.BORDER_CONSTANT,
    ) - binary
    endpoint_pixels = {
        (int(x), int(y))
        for y, x in zip(*np.nonzero((binary > 0) & (neighbour_count == 1)))
    }
    height, width = confidence.shape[:2]
    internal_endpoints = [
        point
        for point in endpoint_pixels
        if (
            border_margin_px <= point[0] < width - border_margin_px
            and border_margin_px <= point[1] < height - border_margin_px
        )
    ]
    if not internal_endpoints:
        return working

    endpoint_directions = {
        point: _skeleton_endpoint_direction(binary, point)
        for point in internal_endpoints
    }
    connectors: list[Polyline] = []
    unresolved = set(internal_endpoints)
    pair_candidates = sorted(
        (
            (
                _endpoint_pair_score(
                    first,
                    endpoint_directions[first],
                    second,
                    endpoint_directions[second],
                ),
                first,
                second,
            )
            for index, first in enumerate(internal_endpoints)
            for second in internal_endpoints[index + 1 :]
            if (
                math.dist(first, second) <= max_gap_px
                and _endpoint_pair_score(
                    first,
                    endpoint_directions[first],
                    second,
                    endpoint_directions[second],
                )
                is not None
            )
        ),
        key=lambda item: float(item[0]),
    )
    for _, first_pixel, second_pixel in pair_candidates:
        if first_pixel not in unresolved or second_pixel not in unresolved:
            continue
        first_point = _nearest_path_endpoint(first_pixel, working)
        second_point = _nearest_path_endpoint(second_pixel, working)
        if first_point is None or second_point is None:
            continue
        first_raster_point = (float(first_pixel[0]), float(first_pixel[1]))
        second_raster_point = (float(second_pixel[0]), float(second_pixel[1]))
        route = _forced_gap_route(
            confidence,
            first_raster_point,
            second_raster_point,
            max_gap_px=max_gap_px,
        )
        connectors.append(
            _deduplicate_adjacent_points(
                [first_point, first_raster_point]
                + route[1:-1]
                + [second_raster_point, second_point]
            )
        )
        unresolved.remove(first_pixel)
        unresolved.remove(second_pixel)

    for endpoint_pixel in sorted(unresolved):
        source_point = _nearest_path_endpoint(endpoint_pixel, working)
        if source_point is None:
            continue
        raster_target = _directional_network_target(
            endpoint_pixel,
            endpoint_directions[endpoint_pixel],
            binary,
            confidence,
            excluded_endpoints=endpoint_pixels,
            max_gap_px=max_gap_px,
        )
        if raster_target is None:
            continue
        target_point = _nearest_polyline_point(
            raster_target,
            working,
            minimum_distance=0.0,
            maximum_distance=5.0,
        )
        if target_point is None:
            target_point = raster_target
        raster_point = (float(endpoint_pixel[0]), float(endpoint_pixel[1]))
        route = _forced_gap_route(
            confidence,
            raster_point,
            raster_target,
            max_gap_px=max_gap_px,
        )
        connectors.append(
            _deduplicate_adjacent_points(
                [source_point, raster_point] + route[1:-1] + [raster_target, target_point]
            )
        )

    return working + connectors


def _skeleton_endpoint_direction(
    binary: np.ndarray,
    endpoint: tuple[int, int],
    *,
    trace_distance_px: float = 14.0,
) -> Point:
    height, width = binary.shape[:2]
    start = endpoint
    current = endpoint
    previous: tuple[int, int] | None = None
    visited = {endpoint}

    for _ in range(max(8, int(trace_distance_px * 3))):
        neighbours = [
            (current[0] + dx, current[1] + dy)
            for dx, dy in NEIGHBOUR_OFFSETS
            if (
                0 <= current[0] + dx < width
                and 0 <= current[1] + dy < height
                and binary[current[1] + dy, current[0] + dx] > 0
                and (current[0] + dx, current[1] + dy) != previous
                and (current[0] + dx, current[1] + dy) not in visited
            )
        ]
        if not neighbours:
            break
        next_point = max(
            neighbours,
            key=lambda point: math.dist(point, start),
        )
        previous, current = current, next_point
        visited.add(current)
        if math.dist(start, current) >= trace_distance_px:
            break

    direction = (float(start[0] - current[0]), float(start[1] - current[1]))
    length = math.hypot(*direction)
    if length <= 1e-6:
        return (0.0, 0.0)
    return (direction[0] / length, direction[1] / length)


def _endpoint_pair_score(
    first: Point,
    first_direction: Point,
    second: Point,
    second_direction: Point,
) -> float | None:
    distance = math.dist(first, second)
    if distance <= 2.0:
        return None
    bridge = (
        (second[0] - first[0]) / distance,
        (second[1] - first[1]) / distance,
    )
    first_alignment = first_direction[0] * bridge[0] + first_direction[1] * bridge[1]
    second_alignment = second_direction[0] * -bridge[0] + second_direction[1] * -bridge[1]
    if min(first_alignment, second_alignment) < -0.35:
        return None
    if first_alignment + second_alignment < -0.05:
        return None
    return distance * (
        2.4
        - max(-0.35, first_alignment)
        - max(-0.35, second_alignment)
    )


def _directional_network_target(
    endpoint: tuple[int, int],
    direction: Point,
    binary: np.ndarray,
    confidence: np.ndarray,
    *,
    excluded_endpoints: set[tuple[int, int]],
    max_gap_px: float,
) -> Point | None:
    excluded = _local_skeleton_pixels(
        binary,
        endpoint,
        max_steps=max(42, int(max_gap_px * 0.28)),
    )
    ys, xs = np.nonzero(binary > 0)
    best: tuple[float, Point] | None = None
    for x_value, y_value in zip(xs, ys):
        point = (int(x_value), int(y_value))
        if point in excluded or point in excluded_endpoints:
            continue
        distance = math.dist(endpoint, point)
        if distance < 8.0 or distance > max_gap_px:
            continue
        bridge = (
            (point[0] - endpoint[0]) / distance,
            (point[1] - endpoint[1]) / distance,
        )
        alignment = direction[0] * bridge[0] + direction[1] * bridge[1]
        if alignment < -0.12:
            continue
        support = float(confidence[point[1], point[0]])
        score = distance * (1.35 - 0.55 * alignment) - support * 18.0
        candidate = (score, (float(point[0]), float(point[1])))
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best[1] if best is not None else None


def _local_skeleton_pixels(
    binary: np.ndarray,
    start: tuple[int, int],
    *,
    max_steps: int,
) -> set[tuple[int, int]]:
    height, width = binary.shape[:2]
    visited = {start}
    queue: deque[tuple[tuple[int, int], int]] = deque([(start, 0)])
    while queue:
        point, steps = queue.popleft()
        if steps >= max_steps:
            continue
        for dx, dy in NEIGHBOUR_OFFSETS:
            neighbour = (point[0] + dx, point[1] + dy)
            if (
                neighbour in visited
                or not (0 <= neighbour[0] < width and 0 <= neighbour[1] < height)
                or binary[neighbour[1], neighbour[0]] == 0
            ):
                continue
            visited.add(neighbour)
            queue.append((neighbour, steps + 1))
    return visited


def _deduplicate_adjacent_points(path: Polyline) -> Polyline:
    output: Polyline = []
    for point in path:
        if not output or math.dist(output[-1], point) > 1e-6:
            output.append(point)
    return output


def _internal_endpoint_count(
    polylines: list[Polyline],
    shape: tuple[int, ...],
    *,
    border_margin_px: int,
) -> int:
    raster = _rasterize_polylines(shape, polylines)
    skeleton = _skeletonize_mask(raster)
    binary = (skeleton > 0).astype(np.uint8)
    neighbour_count = cv2.filter2D(
        binary,
        cv2.CV_16S,
        np.ones((3, 3), dtype=np.uint8),
        borderType=cv2.BORDER_CONSTANT,
    ) - binary
    height, width = binary.shape[:2]
    ys, xs = np.nonzero((binary > 0) & (neighbour_count == 1))
    return sum(
        border_margin_px <= x < width - border_margin_px
        and border_margin_px <= y < height - border_margin_px
        for x, y in zip(xs, ys)
    )


def _prune_internal_terminal_paths(
    polylines: list[Polyline],
    shape: tuple[int, ...],
    *,
    border_margin_px: int,
    max_terminal_length_px: float,
) -> list[Polyline]:
    working = [list(path) for path in polylines if len(path) >= 2]

    for _ in range(5):
        raster = _rasterize_polylines(shape, working)
        skeleton = _skeletonize_mask(raster)
        binary = (skeleton > 0).astype(np.uint8)
        neighbour_count = cv2.filter2D(
            binary,
            cv2.CV_16S,
            np.ones((3, 3), dtype=np.uint8),
            borderType=cv2.BORDER_CONSTANT,
        ) - binary
        height, width = binary.shape[:2]
        ys, xs = np.nonzero((binary > 0) & (neighbour_count == 1))
        endpoints = [
            (int(x), int(y))
            for x, y in zip(xs, ys)
            if (
                border_margin_px <= x < width - border_margin_px
                and border_margin_px <= y < height - border_margin_px
            )
        ]
        if not endpoints:
            break

        remove_indices: set[int] = set()
        for endpoint in endpoints:
            best: tuple[float, int] | None = None
            for index, path in enumerate(working):
                if _polyline_length(path) > max_terminal_length_px:
                    continue
                for path_endpoint in (path[0], path[-1]):
                    distance = math.dist(endpoint, path_endpoint)
                    if distance <= 5.0 and (best is None or distance < best[0]):
                        best = (distance, index)
            if best is not None:
                remove_indices.add(best[1])

        if not remove_indices:
            break
        working = [
            path
            for index, path in enumerate(working)
            if index not in remove_indices
        ]

    return working


def _forced_gap_route(
    confidence: np.ndarray,
    start: Point,
    end: Point,
    *,
    max_gap_px: float,
) -> Polyline:
    supported = _supported_gap_route(
        confidence,
        start,
        end,
        max_gap_px=max_gap_px,
        min_support_fraction=0.0,
        min_mean_confidence=0.0,
        max_unsupported_run=max(confidence.shape),
        max_length_ratio=2.5,
    )
    route = supported[0] if supported is not None else [start, end]
    return _smooth_polyline(route, passes=2)


def _nearest_path_endpoint(
    point: Point,
    polylines: list[Polyline],
    *,
    maximum_distance: float = 5.0,
) -> Point | None:
    best: tuple[float, Point] | None = None
    for path in polylines:
        for endpoint in (path[0], path[-1]):
            distance = math.dist(point, endpoint)
            if distance > maximum_distance:
                continue
            if best is None or distance < best[0]:
                best = (distance, endpoint)
    return best[1] if best is not None else None


def _nearest_polyline_point(
    point: Point,
    polylines: list[Polyline],
    *,
    minimum_distance: float = 0.0,
    maximum_distance: float = math.inf,
) -> Point | None:
    best: tuple[float, Point] | None = None
    for path in polylines:
        for segment_index in range(len(path) - 1):
            nearest = _nearest_point_on_segment(
                point,
                path[segment_index],
                path[segment_index + 1],
            )
            distance = math.dist(point, nearest)
            if distance < minimum_distance or distance > maximum_distance:
                continue
            if best is None or distance < best[0]:
                best = (distance, nearest)
    return best[1] if best is not None else None


def _nearest_point_on_segment(point: Point, start: Point, end: Point) -> Point:
    segment_x = end[0] - start[0]
    segment_y = end[1] - start[1]
    length_squared = segment_x * segment_x + segment_y * segment_y
    if length_squared <= 1e-9:
        return start

    projection = (
        (point[0] - start[0]) * segment_x + (point[1] - start[1]) * segment_y
    ) / length_squared
    projection = _clamp(projection, 0.0, 1.0)
    return (
        start[0] + projection * segment_x,
        start[1] + projection * segment_y,
    )


def _pixel_neighbours(pixel: tuple[int, int], pixels: set[tuple[int, int]]) -> list[tuple[int, int]]:
    x, y = pixel
    return [(x + dx, y + dy) for dx, dy in NEIGHBOUR_OFFSETS if (x + dx, y + dy) in pixels]


def _walk_skeleton_path(
    start: tuple[int, int],
    first: tuple[int, int],
    neighbour_cache: dict[tuple[int, int], list[tuple[int, int]]],
    visited_edges: set[tuple[Point, Point]],
) -> Polyline:
    path: Polyline = [(float(start[0]), float(start[1]))]
    previous = start
    current = first

    while True:
        visited_edges.add(_edge_key(previous, current))
        path.append((float(current[0]), float(current[1])))
        neighbours = neighbour_cache[current]
        if len(neighbours) != 2:
            break
        next_candidates = [item for item in neighbours if item != previous]
        if not next_candidates:
            break
        next_pixel = next_candidates[0]
        edge = _edge_key(current, next_pixel)
        if edge in visited_edges:
            break
        previous, current = current, next_pixel

    return path


def _edge_key(a: tuple[int, int] | Point, b: tuple[int, int] | Point) -> tuple[Point, Point]:
    pa = (float(a[0]), float(a[1]))
    pb = (float(b[0]), float(b[1]))
    return (pa, pb) if pa <= pb else (pb, pa)


def _append_polyline(
    polylines: list[Polyline],
    path: Polyline,
    min_length_px: float,
    simplify_tolerance: float,
) -> None:
    if len(path) < 2:
        return
    if _polyline_length(path) < min_length_px:
        return
    polylines.append(_simplify_polyline(path, simplify_tolerance))


def _contours_to_polylines(
    mask: np.ndarray,
    min_length_px: float,
    simplify_tolerance: float,
) -> list[Polyline]:
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    polylines: list[Polyline] = []

    for contour in contours:
        if len(contour) < 4:
            continue
        length = cv2.arcLength(contour, closed=True)
        if length < min_length_px:
            continue
        approx = cv2.approxPolyDP(contour, simplify_tolerance, closed=True)
        points = [(float(point[0][0]), float(point[0][1])) for point in approx]
        if len(points) >= 3:
            points.append(points[0])
            polylines.append(points)

    return polylines


def _simplify_polyline(path: Polyline, tolerance: float) -> Polyline:
    if tolerance <= 0 or len(path) < 3:
        return path
    contour = np.array(path, dtype=np.float32).reshape((-1, 1, 2))
    approx = cv2.approxPolyDP(contour, tolerance, closed=False)
    simplified = [(float(point[0][0]), float(point[0][1])) for point in approx]
    return simplified if len(simplified) >= 2 else path


def _smooth_polyline(path: Polyline, *, passes: int) -> Polyline:
    if passes <= 0 or len(path) < 3:
        return path

    closed = math.dist(path[0], path[-1]) <= 1.5
    working = list(path[:-1] if closed else path)
    for _ in range(passes):
        if len(working) < 3:
            break
        smoothed: Polyline = []
        if not closed:
            smoothed.append(working[0])
        pair_count = len(working) if closed else len(working) - 1
        for index in range(pair_count):
            first = working[index]
            second = working[(index + 1) % len(working)]
            smoothed.append(
                (
                    first[0] * 0.75 + second[0] * 0.25,
                    first[1] * 0.75 + second[1] * 0.25,
                )
            )
            smoothed.append(
                (
                    first[0] * 0.25 + second[0] * 0.75,
                    first[1] * 0.25 + second[1] * 0.75,
                )
            )
        if not closed:
            smoothed.append(working[-1])
        working = smoothed

    if closed and working:
        working.append(working[0])
    return working


def _is_axis_aligned_reflection(path: Polyline) -> bool:
    if len(path) < 2:
        return False

    length = _polyline_length(path)
    if length < 35.0:
        return False

    chord = math.dist(path[0], path[-1])
    if chord / max(length, 1e-9) < 0.99:
        return False

    dx = path[-1][0] - path[0][0]
    dy = path[-1][1] - path[0][1]
    angle = abs(math.degrees(math.atan2(dy, dx))) % 90.0
    distance_to_axis = min(angle, 90.0 - angle)
    return distance_to_axis <= 2.0


def _polyline_length(path: Iterable[Point]) -> float:
    total = 0.0
    previous: Point | None = None
    for point in path:
        if previous is not None:
            total += math.dist(previous, point)
        previous = point
    return total


def _scale_polylines_to_source(polylines: list[Polyline], resize_ratio: float) -> list[Polyline]:
    if resize_ratio == 1.0:
        return polylines
    return [[(x / resize_ratio, y / resize_ratio) for x, y in polyline] for polyline in polylines]


def _rasterize_polylines(shape: tuple[int, ...], polylines: list[Polyline]) -> np.ndarray:
    height, width = shape[:2]
    output = np.zeros((height, width), dtype=np.uint8)
    for polyline in polylines:
        if len(polyline) < 2:
            continue
        points = np.array(
            [[(int(round(x)), int(round(y))) for x, y in polyline]],
            dtype=np.int32,
        )
        closed = len(polyline) > 2 and math.dist(polyline[0], polyline[-1]) <= 1.5
        cv2.polylines(output, points, isClosed=closed, color=255, thickness=2, lineType=cv2.LINE_8)
    return output


def _write_preview(
    image: np.ndarray,
    work_area: WorkArea,
    mask: np.ndarray,
    polylines: list[Polyline],
    style: ProcessingStyle,
    output_path: Path,
) -> None:
    x0, y0 = work_area.x, work_area.y
    x1, y1 = x0 + work_area.width, y0 + work_area.height
    preview = image[y0:y1, x0:x1].copy()

    # The mask is saved separately; the preview should show the final toolpath.
    _ = mask

    for polyline in polylines:
        if len(polyline) < 2:
            continue
        points = np.array(
            [[(int(round(x)), int(round(y))) for x, y in polyline]],
            dtype=np.int32,
        )
        closed = len(polyline) > 2 and math.dist(polyline[0], polyline[-1]) <= 1.5
        cv2.polylines(preview, points, isClosed=closed, color=style.overlay_bgr, thickness=2, lineType=cv2.LINE_AA)

    cv2.rectangle(preview, (0, 0), (preview.shape[1] - 1, preview.shape[0] - 1), (36, 36, 36), 1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), preview)


def _safe_input_name(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}:
        suffix = ".image"
    return f"input{suffix}"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _resolve_scale(
    fallback_mm_per_pixel: float,
    slab_width_mm: float | None,
    slab_height_mm: float | None,
    width_px: float,
    height_px: float,
) -> tuple[float, bool]:
    ratios: list[float] = []
    if slab_width_mm and slab_width_mm > 0 and width_px > 0:
        ratios.append(float(slab_width_mm) / width_px)
    if slab_height_mm and slab_height_mm > 0 and height_px > 0:
        ratios.append(float(slab_height_mm) / height_px)

    if ratios:
        return _clamp(sum(ratios) / len(ratios), 0.001, 100.0), True

    return _clamp(fallback_mm_per_pixel, 0.001, 100.0), False
