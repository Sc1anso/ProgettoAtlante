import stat
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZipInfo

from app.colmap_dataset import validate_colmap_archive


class ColmapArchiveValidationTests(unittest.TestCase):
    def make_archive(self, entries: dict[str, bytes]) -> Path:
        archive_path = Path(self.temp_dir.name) / "dataset.zip"
        with ZipFile(archive_path, "w") as archive:
            for name, contents in entries.items():
                archive.writestr(name, contents)
        return archive_path

    @staticmethod
    def valid_entries(prefix: str = "") -> dict[str, bytes]:
        return {
            f"{prefix}images/0001.jpg": b"image",
            f"{prefix}sparse/0/cameras.bin": b"cameras",
            f"{prefix}sparse/0/images.bin": b"images",
            f"{prefix}sparse/0/points3D.bin": b"points",
        }

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_valid_archive(self):
        layout = validate_colmap_archive(self.make_archive(self.valid_entries()))
        self.assertIsNone(layout.root_prefix)

    def test_valid_external_root_directory(self):
        layout = validate_colmap_archive(self.make_archive(self.valid_entries("scene_densified/")))
        self.assertEqual(layout.root_prefix, PurePosixPath("scene_densified"))

    def test_rejects_zip_slip(self):
        entries = self.valid_entries()
        entries["../outside.txt"] = b"unsafe"
        with self.assertRaisesRegex(ValueError, "non sicuro"):
            validate_colmap_archive(self.make_archive(entries))

    def test_rejects_incomplete_structure(self):
        with self.assertRaisesRegex(ValueError, "struttura dataset non valida"):
            validate_colmap_archive(self.make_archive({"readme.txt": b"missing scene"}))

    def test_rejects_missing_images(self):
        entries = self.valid_entries()
        del entries["images/0001.jpg"]
        with self.assertRaisesRegex(ValueError, "struttura dataset non valida"):
            validate_colmap_archive(self.make_archive(entries))

    def test_rejects_missing_colmap_file(self):
        entries = self.valid_entries()
        del entries["sparse/0/points3D.bin"]
        with self.assertRaisesRegex(ValueError, "struttura dataset non valida"):
            validate_colmap_archive(self.make_archive(entries))


if __name__ == "__main__":
    unittest.main()
