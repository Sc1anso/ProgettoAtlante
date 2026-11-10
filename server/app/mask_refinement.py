"""Generate and refine foreground masks after unmasked COLMAP processing.

COLMAP sees the original frames to estimate camera poses reliably. This script
then optionally whites the background only in the undistorted images consumed
by RaDe-GS. It intentionally uses inexpensive OpenCV operations after rembg.
"""

import argparse
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image
from rembg import new_session, remove


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def largest_stable_component(mask: np.ndarray, previous: Optional[np.ndarray]) -> np.ndarray:
    """Keep the subject component, preferring one consistent with the last frame."""
    binary = (mask > 127).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if count <= 1:
        return binary * 255

    image_area = binary.shape[0] * binary.shape[1]
    best_label, best_score = 0, -1.0
    for label in range(1, count):
        area = stats[label, cv2.CC_STAT_AREA]
        if area < max(32, image_area * 0.0002):
            continue
        component = labels == label
        # The foreground subject is normally the largest connected component.
        # If several components compete, temporal overlap prevents a nearby
        # environmental object from being selected in a single noisy frame.
        score = float(area) / image_area
        if previous is not None and previous.shape == binary.shape:
            overlap = np.count_nonzero(component & (previous > 0))
            score += 0.35 * overlap / max(area, 1)
        if score > best_score:
            best_label, best_score = label, score
    return ((labels == best_label).astype(np.uint8) * 255) if best_label else binary * 255


def image_paths(images_dir: Path):
    return sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)


def refine_masks(images_dir: Path, masks_dir: Path, generate: bool = False, apply_white: bool = False) -> int:
    masks_dir.mkdir(parents=True, exist_ok=True)
    session = new_session("isnet-general-use") if generate else None
    previous = None
    processed = 0
    for image_path in image_paths(images_dir):
        mask_path = masks_dir / f"{image_path.stem}.png"
        if session is not None:
            # Calling the library directly deliberately avoids rembg's CLI,
            # whose optional web UI dependencies are unrelated to workers.
            with Image.open(image_path) as image:
                generated = remove(image.convert("RGB"), session=session, only_mask=True)
            mask = np.asarray(generated.convert("L"))
        else:
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            print(f"MASK_REFINEMENT: maschera assente per {image_path.name}", flush=True)
            continue
        refined = largest_stable_component(mask, previous)
        cv2.imwrite(str(mask_path), refined)
        if apply_white:
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None or image.shape[:2] != refined.shape:
                raise ValueError(f"Immagine non elaborabile per {image_path.name}")
            image[refined == 0] = 255
            cv2.imwrite(str(image_path), image)
        previous = refined
        processed += 1
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine rembg masks for a sequence of RGB frames")
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--masks", type=Path, required=True)
    parser.add_argument("--generate", action="store_true", help="Generate masks with rembg before refinement")
    parser.add_argument("--apply-white", action="store_true", help="White the masked background in the source images")
    args = parser.parse_args()
    if not args.images.is_dir():
        raise ValueError("Cartella frame non trovata")
    if not args.generate and not args.masks.is_dir():
        raise ValueError("Cartella maschere non trovata")
    processed = refine_masks(args.images, args.masks, args.generate, args.apply_white)
    if not processed:
        raise ValueError("Nessuna maschera elaborabile trovata")
    print(f"MASK_REFINEMENT: {processed} maschere raffinate", flush=True)


if __name__ == "__main__":
    main()
