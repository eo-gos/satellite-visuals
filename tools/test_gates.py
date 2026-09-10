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

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index_utils import (UnsafeFolderName, check_folder_name,  # noqa: E402
                         drop_entries, ensure_entry, new_entry,
                         parse_new_specs, unbacked_folders)
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


class ApplyLevelFolderNameTests(unittest.TestCase):
    """The guard has to hold at the tool boundary, not just in the helper: the
    apply tools take the folder name from a JSON key and use it BOTH as the
    index identity and to build satellites/<folder>. A value that validates
    only after stripping would write one path while the index records another.

    These runs are expected to refuse before any write, so they are safe
    against the real tree — a pass means nothing was created."""

    TOOLS = Path(__file__).resolve().parent
    REPO = TOOLS.parent

    def _run(self, new_folders):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"schema": "satellite-visuals/picks/2",
                       "new_folders": new_folders, "photos": {}}, f)
            picks = f.name
        return subprocess.run([sys.executable, str(self.TOOLS / "apply_picks.py"), picks],
                              capture_output=True, text=True)

    # A name no real batch will ever use, so the assertions below stay true
    # whatever folders the repo gains. Naming a real mission here couples the
    # test to repo state: it passed until a batch legitimately created that
    # folder, and then failed for a reason that had nothing to do with the
    # guard it is meant to pin.
    PADDED = " zzz-guard-probe"

    def test_padded_json_key_is_refused_not_silently_trimmed(self):
        before = len(json.load(open(self.REPO / "index.json")))
        result = self._run({self.PADDED: {"missionID": "204", "missionName": "Probe"}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REFUSED", result.stdout + result.stderr)
        satellites = self.REPO / "satellites"
        self.assertFalse((satellites / self.PADDED).exists())
        self.assertFalse((satellites / self.PADDED.strip()).exists(),
                         "the padded key was trimmed into a real directory")
        self.assertEqual(len(json.load(open(self.REPO / "index.json"))), before)

    def test_path_like_json_key_is_refused(self):
        for bad in ("../escape", "a/b", "GOES-16"):
            with self.subTest(folder=bad):
                result = self._run({bad: {"missionID": "1", "missionName": "X"}})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("REFUSED", result.stdout + result.stderr)


class ApplyCleanTwoLaneTests(unittest.TestCase):
    """apply_clean.py is the one documented entry point, and a picks.json may
    carry new folders for either lane. Batch B's shape is the sharp case: 14
    photo-lane new folders and zero esa_clean. Handing every new folder to the
    clean pass dropped them all as unbacked, and the photos pass never saw
    them, so valid public-domain picks were silently skipped.

    Runs against a temp tree with the tools copied in, so REPO resolves there
    and the real repo is untouched. Downloads use file:// URLs — offline."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "satellites").mkdir()
        (self.tmp / "index.json").write_text("[]\n")
        with open(self.tmp / "ATTRIBUTIONS.csv", "w", newline="") as f:
            csv.writer(f).writerow(
                ["path", "title", "creator_or_rights_holder", "source_url",
                 "original_license_or_terms", "license_url_or_notes"])
        tools = self.tmp / "tools"
        tools.mkdir()
        for name in ("apply_clean.py", "apply_picks.py", "index_utils.py",
                     "licenses.py"):
            shutil.copy(Path(__file__).resolve().parent / name, tools / name)
        self.tools = tools
        # a tiny real PNG for each lane to "download"
        from PIL import Image
        self.src = {}
        for name in ("photosat", "cleansat"):
            p = self.tmp / f"{name}-source.png"
            Image.new("RGBA", (40, 30), (10, 20, 30, 255)).save(p)
            self.src[name] = p.as_uri()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _picks(self):
        return {
            "schema": "satellite-visuals/picks/2",
            "new_folders": {
                "photosat": {"missionID": "101", "missionName": "PhotoSat"},
                "cleansat": {"missionID": "102", "missionName": "CleanSat"},
            },
            "photos": {"photosat": {
                "title": "PhotoSat render", "page": "https://example.org/photosat",
                "url": self.src["photosat"], "ext": "png",
                "licence": "Public domain", "rights_holder": "NASA",
                "credit": "NASA", "artist": "NASA"}},
            "esa_clean": {"cleansat": {
                "title": "CleanSat render", "page": "https://example.org/cleansat",
                "url": self.src["cleansat"], "ext": "png",
                "licence": "CC BY-SA 3.0 IGO", "rights_holder": "ESA/ATG medialab",
                "credit": "ESA/ATG medialab", "status": "licensed"}},
        }

    def test_both_lanes_create_their_new_folder(self):
        picks = self.tmp / "picks.json"
        picks.write_text(json.dumps(self._picks()))
        result = subprocess.run(
            [sys.executable, str(self.tools / "apply_clean.py"), str(picks)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         f"apply_clean failed:\n{result.stdout}\n{result.stderr}")

        # files on disk, both lanes
        self.assertTrue((self.tmp / "satellites/photosat/photosat-photo.png").exists())
        self.assertTrue((self.tmp / "satellites/cleansat/cleansat-photo-clean.png").exists())
        for size in (1024, 512):
            self.assertTrue(
                (self.tmp / f"satellites/cleansat/cleansat-photo-clean-{size}px.png").exists())

        # index entries, both lanes
        index = json.load(open(self.tmp / "index.json"))
        by_folder = {e["folder"]: e for e in index}
        self.assertEqual(set(by_folder), {"photosat", "cleansat"})
        self.assertEqual(by_folder["photosat"]["missionID"], "101")
        self.assertEqual(by_folder["photosat"]["imageStatus"], "licensed")
        self.assertEqual(by_folder["cleansat"]["missionID"], "102")
        self.assertEqual(by_folder["cleansat"]["imageLicense"], "CC BY-SA 3.0 IGO")
        # CC lane carries no notice URL — that belongs to the ESA Standard Licence
        self.assertNotIn("licenceNoticeUrl", by_folder["cleansat"])

        # attribution rows, both lanes
        paths = {r[0] for r in csv.reader(open(self.tmp / "ATTRIBUTIONS.csv"))}
        self.assertIn("satellites/photosat/photosat-photo.png", paths)
        self.assertIn("satellites/cleansat/cleansat-photo-clean.png", paths)
        self.assertIn("satellites/cleansat/cleansat-photo-clean-512px.png", paths)

    def _run_clean(self, data):
        picks = self.tmp / "picks.json"
        picks.write_text(json.dumps(data))
        return subprocess.run(
            [sys.executable, str(self.tools / "apply_clean.py"), str(picks)],
            capture_output=True, text=True)

    def test_crop_applies_to_display_copies_only(self):
        """ESA permits cropping, so the display copies may be cut from a box —
        but the archival original is what ESA published and must be stored
        untouched."""
        from PIL import Image
        data = self._picks()
        data["esa_clean"]["cleansat"]["crop"] = [10, 5, 20, 15]
        result = self._run_clean(data)
        self.assertEqual(result.returncode, 0,
                         f"{result.stdout}\n{result.stderr}")
        d = self.tmp / "satellites/cleansat"
        with Image.open(d / "cleansat-photo-clean.png") as archival:
            self.assertEqual(archival.size, (40, 30), "archival must be unmodified")
        for size in (1024, 512):
            with Image.open(d / f"cleansat-photo-clean-{size}px.png") as disp:
                # 20x15 crop, never upscaled
                self.assertEqual(disp.size, (20, 15))
        note = [r[5] for r in csv.reader(open(self.tmp / "ATTRIBUTIONS.csv"))
                if r and r[0].endswith("cleansat-photo-clean-512px.png")][0]
        self.assertIn("cropped to 10,5,20,15 of the original", note)
        self.assertIn("no matting", note)

    def test_crop_outside_the_image_is_refused(self):
        """Clamping silently would ship a different crop than the reviewer
        approved, so an out-of-bounds box fails the folder outright."""
        for box in ([0, 0, 500, 10], [35, 0, 10, 10], [-5, 0, 10, 10],
                    [0, 0, 0, 10]):
            with self.subTest(box=box):
                data = self._picks()
                data["esa_clean"]["cleansat"]["crop"] = box
                result = self._run_clean(data)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.tmp / "satellites/cleansat").exists())

    def test_clean_lane_download_failure_fails_the_run(self):
        """A clean-lane new folder whose file will not fetch must fail the
        command, not just print a warning and exit 0. Offline: the URL is a
        file:// path that does not exist."""
        data = self._picks()
        data["esa_clean"]["cleansat"]["url"] = (self.tmp / "no-such-file.png").as_uri()
        result = self._run_clean(data)
        self.assertNotEqual(result.returncode, 0,
                            f"expected non-zero:\n{result.stdout}\n{result.stderr}")
        out = result.stdout + result.stderr
        self.assertIn("cleansat", out)
        self.assertFalse((self.tmp / "satellites/cleansat").exists())
        folders = {e["folder"] for e in json.load(open(self.tmp / "index.json"))}
        self.assertNotIn("cleansat", folders)
        # the healthy photo lane still applied
        self.assertIn("photosat", folders)
        self.assertTrue((self.tmp / "satellites/photosat/photosat-photo.png").exists())

    def test_clean_lane_refused_licence_fails_the_run(self):
        """A licence the clean lane does not accept is a refusal, not a
        no-op: the folder must not be created and the run must fail."""
        data = self._picks()
        data["esa_clean"]["cleansat"]["licence"] = "Public domain"
        result = self._run_clean(data)
        self.assertNotEqual(result.returncode, 0,
                            f"expected non-zero:\n{result.stdout}\n{result.stderr}")
        self.assertIn("cleansat", result.stdout + result.stderr)
        self.assertFalse((self.tmp / "satellites/cleansat").exists())
        folders = {e["folder"] for e in json.load(open(self.tmp / "index.json"))}
        self.assertNotIn("cleansat", folders)

    def test_a_new_folder_with_no_pick_in_either_lane_is_dropped(self):
        data = self._picks()
        data["new_folders"]["ghostsat"] = {"missionID": "999", "missionName": "Ghost"}
        result = self._run_clean(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ghostsat", result.stdout + result.stderr)
        self.assertFalse((self.tmp / "satellites/ghostsat").exists())
        folders = {e["folder"] for e in json.load(open(self.tmp / "index.json"))}
        self.assertEqual(folders, {"photosat", "cleansat"})


class ApplyPicksExitCodeTests(unittest.TestCase):
    """A DROP that exits 0 reads as success — to a person skimming output and
    to apply_clean, which runs this as a subprocess with check=True. Any
    requested folder that ends unbacked must fail the run.

    Refusal/no-op runs, so safe against the real tree."""

    TOOLS = Path(__file__).resolve().parent
    REPO = TOOLS.parent

    def _run(self, payload):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            picks = f.name
        return subprocess.run([sys.executable, str(self.TOOLS / "apply_picks.py"), picks],
                              capture_output=True, text=True)

    def test_new_folder_with_no_matching_pick_exits_non_zero(self):
        before = len(json.load(open(self.REPO / "index.json")))
        result = self._run({"schema": "satellite-visuals/picks/2",
                            "new_folders": {"ghostsat": {"missionID": "999",
                                                         "missionName": "Ghost"}},
                            "photos": {}})
        self.assertNotEqual(result.returncode, 0,
                            "an unbacked new folder must fail the run, not print DROP and exit 0")
        self.assertIn("ghostsat", result.stdout + result.stderr)
        self.assertFalse((self.REPO / "satellites" / "ghostsat").exists())
        self.assertEqual(len(json.load(open(self.REPO / "index.json"))), before)

    def test_no_new_folders_at_all_is_a_clean_no_op(self):
        result = self._run({"schema": "satellite-visuals/picks/2", "photos": {}})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class UnbackedFolderTests(unittest.TestCase):
    """A folder created by an apply run is only real once its pick has applied.
    An entry with no photo and no ATTRIBUTIONS row reads as covered when it is
    not, and the portal would resolve the mission to an empty directory."""

    def test_folder_with_no_matching_pick_is_unbacked(self):
        self.assertEqual(unbacked_folders({"terra", "ghostsat"}, {"terra"}),
                         ["ghostsat"])

    def test_folder_whose_pick_failed_is_unbacked(self):
        # the caller drops the folder from `applied` on a download failure
        self.assertEqual(unbacked_folders({"pace"}, set()), ["pace"])

    def test_every_folder_applied_leaves_nothing_to_drop(self):
        self.assertEqual(unbacked_folders({"terra", "aqua"}, {"terra", "aqua"}), [])

    def test_a_pre_existing_folder_is_never_dropped(self):
        """Only folders this run CREATED are candidates. A pick that fails for
        a folder already in the index must not delete that entry."""
        self.assertEqual(unbacked_folders(set(), {"goes-16"}), [])

    def test_drop_entries_removes_only_the_named_folders(self):
        index = [{"folder": "terra"}, {"folder": "ghostsat"}, {"folder": "aqua"}]
        removed = drop_entries(index, ["ghostsat"])
        self.assertEqual(removed, 1)
        self.assertEqual([e["folder"] for e in index], ["terra", "aqua"])

    def test_drop_entries_matches_the_old_index_shape_too(self):
        """folder_of() falls back to SVGColourPath, so a pre-migration row is
        still addressable."""
        index = [{"SVGColourPath": "satellites/ghostsat/ghostsat.svg"},
                 {"folder": "terra"}]
        self.assertEqual(drop_entries(index, ["ghostsat"]), 1)
        self.assertEqual([e.get("folder") for e in index], ["terra"])

    def test_drop_entries_is_a_no_op_for_an_unknown_folder(self):
        index = [{"folder": "terra"}]
        self.assertEqual(drop_entries(index, ["nosuch"]), 0)
        self.assertEqual(len(index), 1)


if __name__ == "__main__":
    unittest.main()
