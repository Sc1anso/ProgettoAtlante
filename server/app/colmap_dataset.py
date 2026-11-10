"""Safe validation and extraction of preprocessed COLMAP scene archives."""

import shutil
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional
from zipfile import BadZipFile, ZipFile, ZipInfo

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
REQUIRED_COLMAP_FILES = (
    PurePosixPath("sparse/0/cameras.bin"),
    PurePosixPath("sparse/0/images.bin"),
    PurePosixPath("sparse/0/points3D.bin"),
)
MAX_ARCHIVE_FILES = 20_000
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


@dataclass(frozen=True)
class ColmapArchiveLayout:
    """The optional single root directory to remove during extraction."""

    root_prefix: Optional[PurePosixPath]


def _safe_member_path(info: ZipInfo) -> PurePosixPath:
    # Treat backslashes as separators too: otherwise a Windows zip-slip name
    # could become dangerous if reused by a different extraction tool.
    raw_name = info.filename.replace("\\", "/")
    path = PurePosixPath(raw_name)
    if not raw_name or path.is_absolute() or ".." in path.parts:
        raise ValueError("lo ZIP contiene un percorso non sicuro")
    if any(part in {"", "."} for part in path.parts):
        raise ValueError("lo ZIP contiene un percorso non valido")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ValueError("lo ZIP contiene un link simbolico non consentito")
    return path


def _layout_for_paths(paths: set[PurePosixPath]) -> ColmapArchiveLayout:
    def has_layout(prefix: Optional[PurePosixPath]) -> bool:
        def joined(relative: PurePosixPath) -> PurePosixPath:
            return relative if prefix is None else prefix / relative

        if not all(joined(required) in paths for required in REQUIRED_COLMAP_FILES):
            return False
        images_dir = joined(PurePosixPath("images"))
        return any(
            len(path.parts) > len(images_dir.parts)
            and path.parts[:len(images_dir.parts)] == images_dir.parts
            and path.suffix.lower() in IMAGE_EXTENSIONS
            for path in paths
        )

    if has_layout(None):
        return ColmapArchiveLayout(None)

    top_levels = {path.parts[0] for path in paths}
    if len(top_levels) == 1:
        prefix = PurePosixPath(next(iter(top_levels)))
        if has_layout(prefix):
            return ColmapArchiveLayout(prefix)

    raise ValueError(
        "struttura dataset non valida: sono richiesti images/ con immagini PNG/JPG/JPEG "
        "e sparse/0/{cameras.bin, images.bin, points3D.bin}"
    )


def validate_colmap_archive(archive_path: Path) -> ColmapArchiveLayout:
    """Validate archive safety and COLMAP layout without extracting anything."""
    try:
        with ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_FILES:
                raise ValueError(f"lo ZIP contiene troppi file (massimo {MAX_ARCHIVE_FILES})")

            paths: set[PurePosixPath] = set()
            total_size = 0
            for info in members:
                path = _safe_member_path(info)
                if info.is_dir():
                    continue
                if path in paths:
                    raise ValueError("lo ZIP contiene file duplicati")
                paths.add(path)
                if info.file_size > MAX_FILE_BYTES:
                    raise ValueError("lo ZIP contiene un file troppo grande")
                total_size += info.file_size
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("lo ZIP supera la dimensione massima decomprimibile")
                if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                    raise ValueError("lo ZIP ha un rapporto di compressione non sicuro")

            if not paths:
                raise ValueError("lo ZIP è vuoto")
            return _layout_for_paths(paths)
    except BadZipFile as exc:
        raise ValueError("il file non è un archivio ZIP valido") from exc


def extract_colmap_archive(archive_path: Path, target_dir: Path) -> Path:
    """Safely extract a validated COLMAP archive and normalize its root folder."""
    layout = validate_colmap_archive(archive_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            source_path = _safe_member_path(info)
            relative_path = source_path if layout.root_prefix is None else source_path.relative_to(layout.root_prefix)
            destination = target_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    return target_dir
