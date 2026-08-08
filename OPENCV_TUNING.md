# OpenCV Tuning Guide

OpenCV itself is not a model that you fine-tune with training data. In this app, OpenCV is a deterministic image-processing pipeline. You improve it by tuning parameters, collecting labeled examples, and eventually training a segmentation model that feeds cleaner masks into the same DXF vectorization pipeline.

## What To Tune First

- `sensitivity`: raises or lowers how many faint vein pixels are accepted.
- `noise_filter`: removes specks and dust; higher values create cleaner but less detailed output.
- `simplify_tolerance`: reduces DXF point count; higher values create smoother, lighter CAD files.
- Slab size fields: calibrate real millimetres before tracing so DXF scale is CNC-ready.

Use the chat box before tracing for quick presets:

```text
make this cleaner and less noisy
capture faint low contrast veins
trace the marked green overlay
create outline/pocket contours
```

## Practical Calibration Workflow

1. Collect 30-100 representative slab photos across stone types, lighting, glare, and vein contrast.
2. For each image, save the desired output as either a binary vein mask or a hand-corrected DXF.
3. Run a grid search over `sensitivity`, `noise_filter`, and `simplify_tolerance`.
4. Score each run against the target using mask IoU/Dice plus CAD checks such as line count, total length, disconnected fragments, and excessive point count.
5. Save the best settings as presets per stone/material type.

## When You Need Real Training

If OpenCV tuning is not enough, train a segmentation model such as U-Net, YOLO segmentation, or SAM/SAM 2 fine-tuning on your labeled vein masks. The trained model should output a clean vein mask; then this app can skeletonize and vectorize that mask into DXF using the existing pipeline.

Recommended data format:

```text
dataset/
  images/
    slab_001.jpg
  masks/
    slab_001.png
  metadata.csv
```

Keep the DXF/vector step separate from model training. The AI model should decide where the veins are; OpenCV, scikit-image, and ezdxf should continue handling cleanup, skeletons, contours, and CAD output.
