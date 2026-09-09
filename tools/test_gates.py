#!/usr/bin/env python3
"""Regression tests for the repo's gates.

Three gates are pinned here: the cut gate in process_photos.process_folder, the
icon gate in licenses.permits_icon_derivation (may a silhouette be published
from this photo?), and the folder-name gate in index_utils, which is a security
boundary — the apply tools mkdir and write under satellites/<folder>, so a
path-like value must be refused before it reaches the filesystem.

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
from index_utils import (UnsafeFolderName, check_folder_name,  # noqa: E402
                         ensure_entry, new_entry, parse_new_specs)
from licenses import permits_icon_derivation  # noqa: E402
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


class IconGateTests(unittest.TestCase):
    """permits_icon_derivation() is deliberately narrower than the cut gate: an
    icon is a new published derivative, so only public domain and
    adaptation-permitting CC qualify. There is no override to test — by
    design, the function takes only a licence name."""

    def test_public_domain_and_cc_allowed(self):
        for licence in ("Public domain", "Public domain (NASA)", "CC0", "CC0 1.0",
                        "CC BY 4.0", "CC BY-SA 3.0", "CC BY-SA 3.0 igo"):
            with self.subTest(licence=licence):
                self.assertTrue(permits_icon_derivation(licence))

    def test_esa_standard_licence_refused(self):
        """ESA refused background removal in writing (ESA HQ PHOTOS
        20260819-0333); a silhouette is exactly that. Never derivable."""
        self.assertFalse(permits_icon_derivation("ESA Standard Licence"))
        self.assertFalse(permits_icon_derivation("esa standard licence"))

    def test_nonfree_and_unrecognised_refused(self):
        for licence in ("media-terms", "trademark-editorial-use",
                        "CC BY-NC 4.0", "CC BY-ND 4.0", "CC BY-NC-SA 4.0",
                        "OGL v3", "All rights reserved", "", "Some New Licence"):
            with self.subTest(licence=licence):
                self.assertFalse(permits_icon_derivation(licence))

    def test_gate_is_a_subset_of_the_cut_gate(self):
        """Anything the icon gate allows, the cut gate must allow too — the
        icon is derived from the cutout, so the looser gate cannot be the one
        that blocks first."""
        from licenses import derivatives_refused, permits_derivatives
        for licence in ("Public domain", "CC0", "CC BY 4.0", "CC BY-SA 3.0 igo",
                        "ESA Standard Licence", "media-terms", "CC BY-ND 4.0"):
            with self.subTest(licence=licence):
                if permits_icon_derivation(licence):
                    self.assertTrue(permits_derivatives(licence))
                    self.assertFalse(derivatives_refused(licence))


class FolderNameGateTests(unittest.TestCase):
    """check_folder_name() is the write-side guard. It runs before any mkdir or
    file write, so every rejection here is a directory that never gets created
    outside satellites/."""

    UNSAFE = ["../escape", "a/b", "GOES-16", ".", "..", "", "./x", "..",
              ".hidden", "x_y", "sat/../..", "Terra", " terra", "terra/"]
    VALID = ["goes-16", "sentinel-2c", "resurs-01-n2", "iss", "terra",
             "suomi-npp", "lageos-1", "a", "9lives", "fy-3c"]

    def test_unsafe_names_refused(self):
        for name in self.UNSAFE:
            with self.subTest(name=name):
                with self.assertRaises(UnsafeFolderName):
                    check_folder_name(name)

    def test_valid_names_accepted(self):
        for name in self.VALID:
            with self.subTest(name=name):
                self.assertEqual(check_folder_name(name), name)

    def test_non_string_refused(self):
        for value in (None, 5, ["terra"], {"folder": "terra"}):
            with self.subTest(value=value):
                with self.assertRaises(UnsafeFolderName):
                    check_folder_name(value)

    def test_new_entry_refuses_before_building_a_row(self):
        with self.assertRaises(UnsafeFolderName):
            new_entry("../escape", "1", "Escape")

    def test_ensure_entry_refuses_and_leaves_the_index_alone(self):
        index = []
        with self.assertRaises(UnsafeFolderName):
            ensure_entry(index, "a/b", "1", "Bad")
        self.assertEqual(index, [])

    def test_cli_new_spec_refuses(self):
        with self.assertRaises(UnsafeFolderName):
            parse_new_specs([["folder=../escape", "missionID=1"]])

    def test_cli_new_spec_accepts_a_valid_folder(self):
        got = parse_new_specs([["folder=radarsat-2", "missionID=352",
                                "missionName=RADARSAT-2"]])
        self.assertEqual(got, {"radarsat-2": {"missionID": "352",
                                              "missionName": "RADARSAT-2"}})


if __name__ == "__main__":
    unittest.main()
