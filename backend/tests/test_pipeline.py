from pathlib import Path

import cv2
import numpy as np

from app.config import Settings
from app.pipeline import processing
from app.pipeline.processing import ProcessingRequest, process_upload


def test_process_upload_creates_preview_and_dxf(tmp_path: Path) -> None:
    image = np.full((300, 520, 3), 245, dtype=np.uint8)
    cv2.line(image, (40, 240), (210, 80), (80, 80, 80), 4)
    cv2.line(image, (210, 80), (420, 210), (120, 120, 120), 3)
    cv2.line(image, (160, 145), (260, 250), (145, 145, 145), 2)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    settings = Settings(storage_dir=tmp_path / "storage", sample_dir=tmp_path / "samples")
    manifest = process_upload(
        image_bytes=encoded.tobytes(),
        request=ProcessingRequest(
            style_id="centerline",
            sensitivity=0.62,
            noise_filter=2,
            simplify_tolerance=1.1,
            mm_per_pixel=0.5,
            slab_width_mm=None,
            slab_height_mm=None,
            original_filename="synthetic.png",
        ),
        settings=settings,
        segmenter=None,
    )

    assert Path(manifest.preview_path).exists()
    assert Path(manifest.dxf_path).exists()
    mask = cv2.imread(manifest.mask_path, cv2.IMREAD_GRAYSCALE)
    preview = cv2.imread(manifest.preview_path, cv2.IMREAD_COLOR)
    assert mask is not None
    assert preview is not None
    assert preview.shape[:2] == mask.shape
    assert 0 < np.count_nonzero(mask) < mask.size * 0.15
    assert manifest.metrics.line_count > 0
    assert manifest.metrics.total_length_mm > 0
    assert manifest.metrics.scale_confirmed is False


def test_stitches_short_aligned_polyline_gaps() -> None:
    fragments = [
        [(0.0, 0.0), (18.0, 0.0)],
        [(23.0, 0.0), (42.0, 1.0)],
        [(47.0, 1.0), (64.0, 1.0)],
    ]

    stitched = processing._stitch_polylines(
        fragments,
        max_gap_px=6.0,
        simplify_tolerance=0.2,
    )

    assert len(stitched) == 1
    assert processing._polyline_length(stitched[0]) > 60


def test_obsolete_hidden_style_falls_back_to_continuous_cnc(tmp_path: Path) -> None:
    image = np.full((240, 420, 3), 245, dtype=np.uint8)
    cv2.line(image, (20, 180), (190, 50), (75, 75, 75), 4)
    cv2.line(image, (190, 50), (390, 170), (100, 100, 100), 3)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    settings = Settings(storage_dir=tmp_path / "storage", sample_dir=tmp_path / "samples")
    manifest = process_upload(
        image_bytes=encoded.tobytes(),
        request=ProcessingRequest(
            style_id="color_trace",
            sensitivity=0.58,
            noise_filter=3,
            simplify_tolerance=1.6,
            mm_per_pixel=1,
            slab_width_mm=None,
            slab_height_mm=None,
            original_filename="raw-slab.png",
        ),
        settings=settings,
        segmenter=None,
    )

    assert manifest.style_id == "centerline"
    mask = cv2.imread(manifest.mask_path, cv2.IMREAD_GRAYSCALE)
    assert mask is not None
    assert np.count_nonzero(mask) > 0


def test_smooth_polyline_preserves_open_endpoints() -> None:
    path = [(0.0, 0.0), (10.0, 8.0), (20.0, -4.0), (30.0, 0.0)]

    smoothed = processing._smooth_polyline(path, passes=2)

    assert smoothed[0] == path[0]
    assert smoothed[-1] == path[-1]
    assert len(smoothed) > len(path)


def test_dangling_endpoint_snaps_to_nearby_segment() -> None:
    paths = [
        [(0.0, 0.0), (8.0, 8.0)],
        [(2.0, 12.0), (16.0, 12.0)],
    ]

    connected = processing._attach_dangling_endpoints(paths, max_gap_px=6.0)

    assert connected[0][-1] == (8.0, 12.0)


def test_pruning_preserves_short_junction_connectors() -> None:
    paths = [
        [(0.0, 0.0), (10.0, 0.0)],
        [(10.0, 0.0), (12.0, 0.0)],
        [(12.0, 0.0), (22.0, 0.0)],
        [(10.0, 0.0), (10.0, 12.0)],
        [(12.0, 0.0), (12.0, 12.0)],
        [(40.0, 40.0), (43.0, 40.0)],
    ]

    pruned = processing._prune_skeleton_segments(paths, min_length_px=10.0)

    assert paths[1] in pruned
    assert paths[-1] not in pruned


def test_skeleton_graph_collapses_junction_cluster() -> None:
    skeleton = np.zeros((80, 80), dtype=np.uint8)
    cv2.line(skeleton, (8, 40), (72, 40), 255, 1)
    cv2.line(skeleton, (40, 8), (40, 72), 255, 1)

    paths = processing._skeleton_graph_to_polylines(skeleton, simplify_tolerance=0.2)
    endpoint_counts: dict[tuple[int, int], int] = {}
    for path in paths:
        for endpoint in (path[0], path[-1]):
            key = processing._point_key(endpoint)
            endpoint_counts[key] = endpoint_counts.get(key, 0) + 1

    assert len(paths) == 4
    assert max(endpoint_counts.values()) == 4


def test_projection_band_can_keep_a_nearly_full_width_slab() -> None:
    values = np.zeros(100, dtype=np.float32)
    values[1:99] = 0.9

    default_band = processing._find_projection_band(
        values,
        thresholds=(0.5,),
        min_fraction=0.35,
    )
    full_width_band = processing._find_projection_band(
        values,
        thresholds=(0.5,),
        min_fraction=0.35,
        allow_full_span=True,
    )

    assert default_band is None
    assert full_width_band == (1, 99)


def test_axis_aligned_reflection_filter_keeps_curved_veins() -> None:
    reflection = [(0.0, 12.0), (60.0, 12.2), (120.0, 12.0)]
    curved_vein = [(0.0, 12.0), (40.0, 18.0), (80.0, 8.0), (120.0, 20.0)]

    assert processing._is_axis_aligned_reflection(reflection) is True
    assert processing._is_axis_aligned_reflection(curved_vein) is False


def test_supported_gap_route_rejects_blank_stone() -> None:
    confidence = np.zeros((50, 70), dtype=np.float32)
    confidence[24:27, 4:24] = 1.0
    confidence[24:27, 46:66] = 1.0

    route = processing._supported_gap_route(
        confidence,
        (22.0, 25.0),
        (48.0, 25.0),
        max_gap_px=30.0,
    )

    assert route is None


def test_supported_gap_route_follows_visible_ridge() -> None:
    confidence = np.zeros((50, 70), dtype=np.float32)
    cv2.line(confidence, (20, 25), (50, 25), 1.0, 3)

    route = processing._supported_gap_route(
        confidence,
        (22.0, 25.0),
        (48.0, 25.0),
        max_gap_px=30.0,
    )

    assert route is not None
    points, support_fraction, length_ratio = route
    assert len(points) >= 2
    assert support_fraction >= 0.68
    assert length_ratio <= 1.55


def test_small_component_connects_to_supported_main_line() -> None:
    paths = [
        [(5.0, 25.0), (55.0, 25.0)],
        [(25.0, 8.0), (28.0, 8.0)],
    ]
    confidence = np.zeros((40, 70), dtype=np.float32)
    cv2.line(confidence, (27, 8), (27, 25), 1.0, 3)

    consolidated = processing._consolidate_small_components(
        paths,
        confidence,
        min_component_length_px=20.0,
        discard_length_px=5.0,
        max_gap_px=24.0,
    )

    assert len(consolidated) == 3
    assert consolidated[-1][0][1] <= 8.0
    assert consolidated[-1][-1][1] >= 25.0


def test_tiny_unsupported_component_is_removed() -> None:
    paths = [
        [(5.0, 25.0), (55.0, 25.0)],
        [(25.0, 8.0), (28.0, 8.0)],
    ]
    confidence = np.zeros((40, 70), dtype=np.float32)

    consolidated = processing._consolidate_small_components(
        paths,
        confidence,
        min_component_length_px=20.0,
        discard_length_px=5.0,
        max_gap_px=24.0,
    )

    assert consolidated == [paths[0]]


def test_component_network_forces_single_connected_mask() -> None:
    paths = [
        [(5.0, 10.0), (25.0, 10.0)],
        [(40.0, 25.0), (60.0, 25.0)],
        [(75.0, 10.0), (95.0, 10.0)],
    ]
    confidence = np.zeros((40, 105), dtype=np.float32)

    connected = processing._connect_component_network(paths, confidence)
    mask = processing._rasterize_polylines(confidence.shape, connected)
    component_count, _ = cv2.connectedComponents((mask > 0).astype(np.uint8), connectivity=8)

    assert len(connected) == len(paths) + 2
    assert component_count == 2


def test_endpoint_closure_removes_internal_dead_ends() -> None:
    paths = [
        [(5.0, 20.0), (35.0, 20.0)],
        [(55.0, 8.0), (55.0, 32.0)],
    ]
    confidence = np.zeros((40, 65), dtype=np.float32)

    closed = processing._close_internal_endpoints(
        paths,
        confidence,
        border_margin_px=4,
        max_gap_px=30.0,
    )
    mask = processing._rasterize_polylines(confidence.shape, closed)
    skeleton = processing._skeletonize_mask(mask) > 0
    padded = np.pad(skeleton.astype(np.uint8), 1)
    neighbour_count = sum(
        padded[
            1 + dy : 1 + dy + skeleton.shape[0],
            1 + dx : 1 + dx + skeleton.shape[1],
        ]
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
    ) - skeleton
    endpoint_count = int(np.count_nonzero(skeleton & (neighbour_count == 1)))

    assert len(closed) > len(paths)
    assert endpoint_count < 4


def test_directional_target_skips_the_endpoints_own_branch() -> None:
    binary = np.zeros((50, 80), dtype=np.uint8)
    cv2.line(binary, (5, 25), (30, 25), 1, 1)
    cv2.line(binary, (50, 10), (50, 40), 1, 1)
    confidence = np.zeros_like(binary, dtype=np.float32)
    confidence[:, 50] = 1.0

    target = processing._directional_network_target(
        (30, 25),
        (1.0, 0.0),
        binary,
        confidence,
        excluded_endpoints={(5, 25), (30, 25), (50, 10), (50, 40)},
        max_gap_px=30.0,
    )

    assert target is not None
    assert target[0] == 50.0


def test_endpoint_pair_rejects_a_connection_behind_both_tips() -> None:
    score = processing._endpoint_pair_score(
        (20.0, 20.0),
        (-1.0, 0.0),
        (40.0, 20.0),
        (1.0, 0.0),
    )

    assert score is None


def test_prunes_short_internal_terminal_path() -> None:
    paths = [
        [(5.0, 20.0), (30.0, 20.0), (55.0, 20.0)],
        [(30.0, 20.0), (30.0, 30.0)],
    ]

    pruned = processing._prune_internal_terminal_paths(
        paths,
        (45, 65),
        border_margin_px=4,
        max_terminal_length_px=15.0,
    )

    assert paths[0] in pruned
    assert paths[1] not in pruned
