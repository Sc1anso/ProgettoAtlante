"""Validation and unpacking for the portable ZED capture contract."""

import struct
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

REQUIRED_ZED_FILES = {"recording.mp4", "depth_data.dp", "camera_data.dp"}


def validate_zed_archive(archive_path: Path) -> None:
    with ZipFile(archive_path) as archive:
        names: set[str] = set()
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("L'archivio ZED contiene un percorso non sicuro")
            if not info.is_dir():
                names.add(info.filename)
        if names != REQUIRED_ZED_FILES:
            required = ", ".join(sorted(REQUIRED_ZED_FILES))
            raise ValueError(f"Lo ZIP ZED deve contenere esattamente nella radice: {required}")
        if archive.getinfo("recording.mp4").file_size == 0:
            raise ValueError("recording.mp4 è vuoto")
        if archive.getinfo("camera_data.dp").file_size < 44:
            raise ValueError("camera_data.dp è troppo piccolo")
        depth_info = archive.getinfo("depth_data.dp")
        if depth_info.file_size < 16:
            raise ValueError("depth_data.dp è troppo piccolo")
        with archive.open("depth_data.dp") as depth_file:
            width, height, fps = struct.unpack("<iif", depth_file.read(12))
        if not (16 <= width <= 10000 and 16 <= height <= 10000 and 1 <= fps <= 240):
            raise ValueError("header di depth_data.dp non valido")
        if depth_info.file_size < 12 + width * height * 4:
            raise ValueError("depth_data.dp non contiene un frame completo")


def extract_zed_archive(archive_path: Path, target_dir: Path) -> Path:
    validate_zed_archive(archive_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive_path) as archive:
        archive.extractall(target_dir)
    return target_dir
