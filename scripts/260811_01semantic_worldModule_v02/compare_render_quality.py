"""Compare strictly matched GUI/script RGB frames with content-aware metrics."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def load_rgb(path: str | Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def parse_roi(text: str | None, width: int, height: int) -> tuple[int, int, int, int]:
    if not text:
        return 0, 0, width, height
    values = [int(value.strip()) for value in text.split(",")]
    if len(values) != 4:
        raise ValueError("ROI must be x,y,width,height")
    x, y, roi_width, roi_height = values
    if x < 0 or y < 0 or roi_width <= 0 or roi_height <= 0:
        raise ValueError("ROI coordinates must be non-negative and size must be positive")
    if x + roi_width > width or y + roi_height > height:
        raise ValueError("ROI exceeds image bounds")
    return x, y, roi_width, roi_height


def luminance(image: np.ndarray) -> np.ndarray:
    values = image.astype(np.float64)
    return 0.2126 * values[..., 0] + 0.7152 * values[..., 1] + 0.0722 * values[..., 2]


def laplacian_variance(values: np.ndarray) -> float:
    if values.shape[0] < 3 or values.shape[1] < 3:
        return 0.0
    center = values[1:-1, 1:-1]
    laplacian = (
        -4.0 * center
        + values[:-2, 1:-1]
        + values[2:, 1:-1]
        + values[1:-1, :-2]
        + values[1:-1, 2:]
    )
    return float(np.var(laplacian))


def global_ssim(reference: np.ndarray, candidate: np.ndarray) -> float:
    reference = reference.astype(np.float64)
    candidate = candidate.astype(np.float64)
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    mean_ref = float(np.mean(reference))
    mean_candidate = float(np.mean(candidate))
    var_ref = float(np.var(reference))
    var_candidate = float(np.var(candidate))
    covariance = float(np.mean((reference - mean_ref) * (candidate - mean_candidate)))
    numerator = (2 * mean_ref * mean_candidate + c1) * (2 * covariance + c2)
    denominator = (mean_ref**2 + mean_candidate**2 + c1) * (
        var_ref + var_candidate + c2
    )
    return float(numerator / denominator) if denominator else 1.0


def compare(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    if reference.shape != candidate.shape:
        raise ValueError(f"Image shapes differ: {reference.shape} != {candidate.shape}")
    ref_luma = luminance(reference)
    candidate_luma = luminance(candidate)
    difference = reference.astype(np.float64) - candidate.astype(np.float64)
    mse = float(np.mean(difference**2))
    rmse = math.sqrt(mse)
    psnr = None if mse == 0 else 20.0 * math.log10(255.0 / rmse)
    return {
        "shape": list(reference.shape),
        "mae": float(np.mean(np.abs(difference))),
        "rmse": rmse,
        "psnr_db": psnr,
        "identical": mse == 0,
        "global_ssim": global_ssim(ref_luma, candidate_luma),
        "reference": {
            "mean_luminance": float(np.mean(ref_luma)),
            "near_black_fraction": float(np.mean(ref_luma < 5.0)),
            "laplacian_variance": laplacian_variance(ref_luma),
        },
        "candidate": {
            "mean_luminance": float(np.mean(candidate_luma)),
            "near_black_fraction": float(np.mean(candidate_luma < 5.0)),
            "laplacian_variance": laplacian_variance(candidate_luma),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--roi", default=None, help="Optional x,y,width,height")
    parser.add_argument("--output-report", default=None)
    args = parser.parse_args()

    reference = load_rgb(args.reference)
    candidate = load_rgb(args.candidate)
    if reference.shape != candidate.shape:
        raise ValueError(f"Image shapes differ: {reference.shape} != {candidate.shape}")
    height, width = reference.shape[:2]
    x, y, roi_width, roi_height = parse_roi(args.roi, width, height)
    report = {
        "reference": str(Path(args.reference).resolve()),
        "candidate": str(Path(args.candidate).resolve()),
        "roi": [x, y, roi_width, roi_height],
        "metrics": compare(
            reference[y : y + roi_height, x : x + roi_width],
            candidate[y : y + roi_height, x : x + roi_width],
        ),
        "comparability": {
            "verified": False,
            "reason": "Image metadata/Stage/camera equality must be checked separately",
        },
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output_report:
        Path(args.output_report).write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
