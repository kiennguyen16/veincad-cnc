from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from app.config import Settings

LOGGER = logging.getLogger(__name__)


@dataclass
class SegmentationResult:
    mask: np.ndarray
    source: str


class Sam2Segmenter:
    """Optional SAM 2 wrapper.

    The app does not require SAM 2. When configured, this class produces a broad
    foreground/line candidate mask that is blended with deterministic OpenCV
    extraction rather than trusted blindly.
    """

    def __init__(self, settings: Settings):
        self.enabled = settings.enable_sam2
        self.available = False
        self.generator = None

        if not self.enabled:
            return

        try:
            import torch
            from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
        except Exception as exc:  # pragma: no cover - depends on optional stack
            LOGGER.warning("SAM 2 requested but unavailable: %s", exc)
            return

        try:  # pragma: no cover - depends on optional stack
            device = settings.sam2_device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"

            if settings.sam2_hf_model:
                predictor = SAM2ImagePredictor.from_pretrained(settings.sam2_hf_model, device=device)
                self.generator = SAM2AutomaticMaskGenerator(predictor.model)
            elif settings.sam2_checkpoint and settings.sam2_model_cfg:
                model = build_sam2(settings.sam2_model_cfg, settings.sam2_checkpoint, device=device)
                self.generator = SAM2AutomaticMaskGenerator(model)
            else:
                LOGGER.warning("SAM 2 is enabled but no model source is configured.")
                return

            self.available = True
        except Exception as exc:
            LOGGER.warning("SAM 2 initialization failed: %s", exc)

    def segment(self, image_bgr: np.ndarray) -> SegmentationResult | None:
        if not self.available or self.generator is None:
            return None

        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        masks = self.generator.generate(image_rgb)  # pragma: no cover - optional stack
        if not masks:
            return None

        combined = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
        image_area = image_bgr.shape[0] * image_bgr.shape[1]

        for item in masks:
            segmentation = item.get("segmentation")
            area = float(item.get("area", 0))
            if segmentation is None or area <= 0:
                continue
            area_ratio = area / image_area
            if 0.0003 <= area_ratio <= 0.25:
                combined[segmentation.astype(bool)] = 255

        if int(combined.sum()) == 0:
            return None

        return SegmentationResult(mask=combined, source="sam2")
