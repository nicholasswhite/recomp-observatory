"""Release package tests; local workspace data must never be distributable."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from package_dashboard import FILES, package
from verify_package import verify


class PackageTests(unittest.TestCase):
    def test_allowlist_has_no_runtime_or_artwork_data(self):
        normalized = [Path(value).as_posix() for value in FILES]
        self.assertEqual(len(normalized), len(set(normalized)))
        self.assertFalse(any(value.startswith("work/") for value in normalized))
        self.assertFalse(any(value.startswith("public/artwork/") for value in normalized))
        self.assertFalse(any(Path(value).is_absolute() for value in normalized))

    def test_generated_package_passes_public_verifier(self):
        scratch = Path(__file__).parent / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            output = Path(temporary) / "release.zip"
            package(output)
            self.assertEqual(verify(output), [])

    def test_verifier_rejects_members_outside_exact_allowlist(self):
        scratch = Path(__file__).parent / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            output = Path(temporary) / "extra.zip"
            with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
                for relative in FILES:
                    archive.write(Path(__file__).parent / relative, "recomp-observatory/" + relative)
                archive.writestr("recomp-observatory/unexpected.txt", "synthetic")
            self.assertTrue(any("unexpected release member" in error for error in verify(output)))

    def test_packager_rejects_missing_allowlisted_member(self):
        scratch = Path(__file__).parent / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary, \
             patch("package_dashboard.FILES", ["definitely-missing.txt"]):
            with self.assertRaisesRegex(ValueError, "Unsafe or missing"):
                package(Path(temporary) / "release.zip")


if __name__ == "__main__":
    unittest.main()
