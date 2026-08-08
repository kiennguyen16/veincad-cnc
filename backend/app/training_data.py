from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


TRAINING_STYLE_IDS = ("centerline", "high_detail")
TRAINING_READINESS_THRESHOLD = 20
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass(frozen=True)
class TrainingFiles:
    source_original_filename: str
    source_stored_filename: str
    source_path: str
    label_original_filename: str
    label_stored_filename: str
    label_path: str


def validate_training_image(image_bytes: bytes, original_filename: str | None, field_name: str) -> tuple[str, str]:
    clean_name = _safe_original_filename(original_filename, f"{field_name}.png")
    suffix = Path(clean_name).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise ValueError(
            f"{field_name} must be a JPG, PNG, BMP, WebP, or TIFF image."
        )

    encoded = np.frombuffer(image_bytes, dtype=np.uint8)
    if encoded.size == 0 or cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED) is None:
        raise ValueError(f"{field_name} is not a readable image.")
    return clean_name, suffix


def persist_training_pair(
    *,
    storage_root: Path,
    style_id: str,
    sample_id: str,
    source_bytes: bytes,
    source_original_filename: str,
    source_suffix: str,
    label_bytes: bytes,
    label_original_filename: str,
    label_suffix: str,
) -> TrainingFiles:
    if style_id not in TRAINING_STYLE_IDS:
        raise ValueError("Unsupported training style.")

    training_root = (storage_root / "training").resolve()
    sample_dir = (training_root / style_id / sample_id).resolve()
    _require_descendant(sample_dir, training_root)
    if sample_dir.parent != (training_root / style_id).resolve():
        raise ValueError("Invalid training sample path.")

    source_stored_filename = f"source{source_suffix}"
    label_stored_filename = f"label{label_suffix}"
    source_file = sample_dir / source_stored_filename
    label_file = sample_dir / label_stored_filename

    sample_dir.mkdir(parents=True, exist_ok=False)
    try:
        source_file.write_bytes(source_bytes)
        label_file.write_bytes(label_bytes)
    except Exception:
        shutil.rmtree(sample_dir, ignore_errors=True)
        raise

    return TrainingFiles(
        source_original_filename=source_original_filename,
        source_stored_filename=source_stored_filename,
        source_path=source_file.relative_to(storage_root.resolve()).as_posix(),
        label_original_filename=label_original_filename,
        label_stored_filename=label_stored_filename,
        label_path=label_file.relative_to(storage_root.resolve()).as_posix(),
    )


def resolve_training_file(storage_root: Path, sample: dict, image_kind: str) -> Path:
    if image_kind not in {"source", "label"}:
        raise ValueError("Unsupported training image type.")

    sample_dir = _validated_sample_dir(storage_root, sample)
    stored_filename = str(sample[f"{image_kind}_stored_filename"])
    relative_path = str(sample[f"{image_kind}_path"])
    candidate = (storage_root.resolve() / relative_path).resolve()
    _require_descendant(candidate, sample_dir)
    if candidate.parent != sample_dir or candidate.name != stored_filename:
        raise ValueError("Training image path does not match its sample.")
    return candidate


def remove_training_sample_files(storage_root: Path, sample: dict) -> None:
    sample_dir = _validated_sample_dir(storage_root, sample)
    resolve_training_file(storage_root, sample, "source")
    resolve_training_file(storage_root, sample, "label")

    if sample_dir.exists():
        if not sample_dir.is_dir() or sample_dir.is_symlink():
            raise ValueError("Training sample storage is not a safe directory.")
        shutil.rmtree(sample_dir)


def _validated_sample_dir(storage_root: Path, sample: dict) -> Path:
    style_id = str(sample["style_id"])
    sample_id = str(sample["id"])
    if style_id not in TRAINING_STYLE_IDS:
        raise ValueError("Training sample has an invalid style.")
    if len(sample_id) != 32 or any(character not in "0123456789abcdef" for character in sample_id.lower()):
        raise ValueError("Training sample has an invalid identifier.")

    training_root = (storage_root / "training").resolve()
    sample_dir = (training_root / style_id / sample_id).resolve()
    _require_descendant(sample_dir, training_root)
    if sample_dir.parent != (training_root / style_id).resolve():
        raise ValueError("Invalid training sample directory.")
    return sample_dir


def _safe_original_filename(filename: str | None, fallback: str) -> str:
    normalized = (filename or "").replace("\\", "/")
    clean_name = Path(normalized).name.strip()
    return clean_name or fallback


def _require_descendant(candidate: Path, root: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Training path escapes the configured storage root.") from exc
