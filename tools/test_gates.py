#!/usr/bin/env python3
"""Regression tests for the licence gates in process_photos.process_folder.

The gates are the repo's legal enforcement point, so they get pinned:
missing index metadata must skip (not sail through on empty strings),
a written refusal must not be overridable, and the ordinary gate must
stay overridable. Runs on Pillow alone — every case exits before matting,
except the happy path, which uses a source-alpha raw so rembg never loads.

    . .venv/bin/activate && python3 -m unittest tools.test_gates -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_photos import DEFAULT_MARGIN, process_folder  # noqa: E402


def make_root(tmp):
    """A minimal repo layout: satellites/testsat/testsat-photo.png with a real
    alpha channel (fully-clear border) so the happy path takes source-alpha."""
    root = Path(tmp)
    folder = root / "satellites" / "testsat"
    folder.mkdir(parents=True)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(16, 48):
        for y in range(16, 48):
            img.putpixel((x, y), (200, 200, 200, 255))
    img.save(folder / "testsat-photo.png")
    return root


def run(root, entry, **kw):
    return process_folder(
        "testsat", entry, root, root, get_session=lambda: None,
        model_name="isnet-general-use", sizes=(32, 16),
        margin=DEFAULT_MARGIN, force=False, **kw,
    )


class LicenceGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_root(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_entry_skips(self):
        rec = run(self.root, None)
        self.assertEqual(rec["status"], "skipped-missing-index")

    def test_incomplete_entry_skips(self):
        rec = run(self.root, {"imageLicense": "CC BY 4.0"})  # no imageStatus
        self.assertEqual(rec["status"], "skipped-missing-index")

    def test_written_refusal_ignores_override(self):
        entry = {"imageLicense": "ESA Standard Licence", "imageStatus": "licensed"}
        rec = run(self.root, entry, allow_nonderiv=True)
        self.assertEqual(rec["status"], "skipped-derivatives-refused")

    def test_ordinary_gate_skips_without_override(self):
        entry = {"imageLicense": "CC BY 4.0", "imageStatus": "media-terms"}
        rec = run(self.root, entry)
        self.assertEqual(rec["status"], "skipped-no-derivatives")

    def test_ordinary_gate_honours_override(self):
        entry = {"imageLicense": "CC BY 4.0", "imageStatus": "media-terms"}
        rec = run(self.root, entry, allow_nonderiv=True)
        self.assertEqual(rec["status"], "ok")

    def test_clean_licence_cuts(self):
        entry = {"imageLicense": "CC BY 4.0", "imageStatus": "licensed"}
        rec = run(self.root, entry)
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["method"], "source-alpha")


if __name__ == "__main__":
    unittest.main()
