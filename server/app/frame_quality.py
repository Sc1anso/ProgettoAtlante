"""Conservatively isolate blurry video frames before COLMAP feature matching."""

import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def sharpness(path: Path) -> float:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return 0.0
    return float(cv2.Laplacian(image, cv2.CV_64F).var())


def filter_blurry_frames(frames_dir: Path) -> dict:
    frames = sorted(path for path in frames_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    scores = {path: sharpness(path) for path in frames}
    valid_scores = np.array([score for score in scores.values() if score > 0], dtype=np.float64)
    if len(frames) < 25 or not len(valid_scores):
        return {"kept": len(frames), "rejected": 0, "threshold": 0.0}

    # Relative threshold works across bright/dark videos. The cap and minimum
    # preserve enough camera viewpoints even for uniformly soft phone videos.
    threshold = max(15.0, float(np.median(valid_scores)) * 0.25)
    candidates = sorted((path for path, score in scores.items() if score < threshold), key=scores.get)
    max_rejected = min(len(frames) - 24, max(1, int(len(frames) * 0.15)))
    rejected = candidates[:max_rejected]
    rejected_dir = frames_dir.parent / "rejected_blurry_frames"
    if rejected:
        rejected_dir.mkdir(exist_ok=True)
        for frame in rejected:
            shutil.move(str(frame), str(rejected_dir / frame.name))
    report = {
        "kept": len(frames) - len(rejected),
        "rejected": len(rejected),
        "threshold": round(threshold, 3),
        "median_sharpness": round(float(np.median(valid_scores)), 3),
    }
    (frames_dir.parent / "frame-quality.json").write_text(json.dumps(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservatively filter blurry RGB video frames")
    parser.add_argument("frames", type=Path)
    args = parser.parse_args()
    if not args.frames.is_dir():
        raise ValueError("Cartella frame non trovata")
    report = filter_blurry_frames(args.frames)
    print(
        "FRAME_FILTER: mantenuti {kept}, scartati {rejected}, soglia nitidezza {threshold}".format(**report),
        flush=True,
    )


if __name__ == "__main__":
    main()
