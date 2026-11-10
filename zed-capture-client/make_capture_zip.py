"""Create the exact portable ZED archive consumed by Pavarotti 3D."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REQUIRED = ("recording.mp4", "depth_data.dp", "camera_data.dp")

parser = argparse.ArgumentParser(description="Package a ZED acquisition for Pavarotti 3D")
parser.add_argument("capture_dir", type=Path, help="Directory produced by capture_video.py")
parser.add_argument("output_zip", type=Path, nargs="?", help="Output ZIP path")
args = parser.parse_args()

source = args.capture_dir.resolve()
output = (args.output_zip or source.with_suffix(".zip")).resolve()
missing = [name for name in REQUIRED if not (source / name).is_file()]
if missing:
    raise SystemExit(f"Missing required capture files: {', '.join(missing)}")

with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=6) as archive:
    for name in REQUIRED:
        archive.write(source / name, arcname=name)
print(output)
