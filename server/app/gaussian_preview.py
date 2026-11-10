"""Create a compact, browser-oriented Gaussian PLY preview."""

import argparse
import gzip
from pathlib import Path

import numpy as np


PLY_TYPES = {
    "char": "i1", "uchar": "u1", "short": "<i2", "ushort": "<u2",
    "int": "<i4", "uint": "<u4", "float": "<f4", "double": "<f8",
}


def read_binary_header(source: Path):
    with source.open("rb") as handle:
        header = bytearray()
        while not header.endswith(b"end_header\n"):
            byte = handle.read(1)
            if not byte or len(header) > 256_000:
                raise ValueError("Header PLY non valido o troppo grande")
            header.extend(byte)
    lines = header.decode("ascii").splitlines()
    if "format binary_little_endian 1.0" not in lines:
        raise ValueError("La preview supporta soltanto PLY binari little-endian")
    count = None
    properties = []
    in_vertex = False
    for line in lines:
        parts = line.split()
        if parts[:2] == ["element", "vertex"]:
            count = int(parts[2])
            in_vertex = True
        elif parts[:1] == ["element"]:
            in_vertex = False
        elif in_vertex and parts[:1] == ["property"]:
            if len(parts) != 3 or parts[1] not in PLY_TYPES:
                raise ValueError("Il PLY usa proprietà non supportate dalla preview")
            properties.append((parts[2], PLY_TYPES[parts[1]]))
    if count is None or not properties:
        raise ValueError("Il PLY non contiene Gaussian validi")
    return bytes(header), lines, count, np.dtype(properties)


def create_preview(source: Path, destination: Path, max_splats: int) -> int:
    header, lines, count, dtype = read_binary_header(source)
    expected_size = len(header) + count * dtype.itemsize
    if source.stat().st_size < expected_size:
        raise ValueError("Il PLY è troncato")
    splats = np.memmap(source, dtype=dtype, mode="r", offset=len(header), shape=(count,))
    selected_count = min(count, max_splats)
    indexes = np.arange(count, dtype=np.int64) if selected_count == count else np.linspace(0, count - 1, selected_count, dtype=np.int64)
    preview = splats[indexes]
    rewritten_lines = [f"element vertex {selected_count}" if line.startswith("element vertex ") else line for line in lines]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destination, "wb", compresslevel=6) as output:
        output.write(("\n".join(rewritten_lines) + "\n").encode("ascii"))
        output.write(preview.tobytes())
    return selected_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera preview Gaussian compressa")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--max-splats", type=int, default=100_000)
    args = parser.parse_args()
    if args.max_splats < 10_000:
        raise ValueError("La preview deve contenere almeno 10.000 Gaussian")
    print(f"GAUSSIAN_PREVIEW_SPLATS: {create_preview(args.source, args.destination, args.max_splats)}", flush=True)


if __name__ == "__main__":
    main()
