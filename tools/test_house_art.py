#!/usr/bin/env python3
"""Regression tests for the house-artwork lane's gates.

Every case here is a failure that actually happened during the two pilots and
was caught by a human rather than by code. Each one is now a test:

  - a drawing shipped an element that was in no reference and in no description
    -> ConsistencyCheckTests
  - a drawing had wings that were correct in 3D and invisible on screen
    -> ProjectionCheckTests
  - an icon must be derived from OUR SVG, never from a photograph
    -> IconDerivationTests
  - a folder must not be applied without the record of what was looked at
    -> ApplyRefusalTests
  - a folder name is a filesystem boundary and must be refused before any write
    -> FolderNameGuardTests

Runs on Pillow alone; no numpy, no network.

    . .venv/bin/activate && python3 -m unittest tools.test_house_art -v
"""

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import apply_art  # noqa: E402
from house_art import checks, kit, schema  # noqa: E402
from index_utils import UnsafeFolderName  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def minimal_description(folder="testsat", **over):
    d = {
        "folder": folder,
        "mission": "Test Satellite",
        "evidence": "B",
        "evidence_note": "one clear render",
        "bus": {"form": "box", "dims_m": [2.0, 2.0, 2.0], "finish": "gold MLI"},
        "solar": {"wings": 2, "panels_per_wing": 3, "mount": "short yokes"},
        "distinctive": "A box with two wings.",
        "references": [
            {"n": 1, "source_page": "https://example.org/spacecraft",
             "image_url": "https://example.org/spacecraft.jpg",
             "credit": "Example Agency", "downloaded": True,
             "used_for_geometry": True},
        ],
    }
    d.update(over)
    return d


def minimal_scene(extra_part=None, hide_wings=False):
    """A box with two wings, tagged the way the lane requires."""
    scene = kit.Scene(kit.Camera(az=32, el=18))
    with scene.part("bus"):
        scene.box((0, 0, 0), (2.0, 2.0, 2.0), "gold")
    with scene.part("solar array"):
        for sgn in (1, -1):
            if hide_wings:
                # entirely inside the bus: correct in 3D, invisible on screen
                scene.wing((sgn * 0.1, -0.2, 0.0), (sgn * 0.2, 0, 0), (0, 0.4, 0),
                           "panel", cols=1)
            else:
                scene.wing((sgn * 1.05, -0.6, 0.2), (sgn * 3.0, 0, 0), (0, 1.2, 0),
                           "panel", cols=3)
    if extra_part:
        with scene.part(extra_part):
            scene.tube((0, 0, 1.05), (0, 0, 1.9), 0.2, "white")
    return scene


class SchemaTests(unittest.TestCase):
    def test_minimal_description_is_valid(self):
        self.assertEqual(schema.validate(minimal_description(), "testsat"), [])

    def test_missing_required_key_is_reported(self):
        d = minimal_description()
        del d["distinctive"]
        self.assertIn("missing required key: distinctive", schema.validate(d, "testsat"))

    def test_evidence_grade_is_an_enum(self):
        d = minimal_description(evidence="great")
        self.assertTrue(any("evidence must be one of" in p
                            for p in schema.validate(d, "testsat")))

    def test_folder_must_match_the_directory(self):
        problems = schema.validate(minimal_description("testsat"), "othersat")
        self.assertTrue(any("does not match" in p for p in problems))

    def test_reference_must_be_a_url(self):
        d = minimal_description()
        d["references"][0]["source_page"] = "satellites/testsat/ref1.jpg"
        self.assertTrue(any("must be a URL" in p for p in schema.validate(d, "testsat")))

    def test_reference_may_not_carry_a_stored_file(self):
        """Reference imagery is consulted, never stored. A path in the committed
        description would mean a file had been kept."""
        d = minimal_description()
        d["references"][0]["file"] = "satellites/testsat/refs/ref1.jpg"
        problems = schema.validate(d, "testsat")
        self.assertTrue(any("never stored in the repository" in p for p in problems))

    def test_at_least_one_reference_must_have_been_used(self):
        d = minimal_description()
        d["references"][0]["used_for_geometry"] = False
        self.assertTrue(any("used_for_geometry" in p
                            for p in schema.validate(d, "testsat")))

    def test_omission_needs_a_reason(self):
        d = minimal_description(deliberately_omitted=[{"element": "star tracker"}])
        self.assertTrue(any("needs element and reason" in p
                            for p in schema.validate(d, "testsat")))

    def test_element_names_are_the_contract(self):
        d = minimal_description(antennas=[{"name": "downlink dish", "form": "paraboloid"}])
        self.assertEqual(schema.element_names(d),
                         {"bus", "solar array", "downlink dish"})


class ConsistencyCheckTests(unittest.TestCase):
    """The GHGSat phantom cylinder, as a test."""

    def test_matching_drawing_passes(self):
        result = checks.check_description(minimal_description(), minimal_scene())
        self.assertTrue(result["ok"], result["problems"])

    def test_phantom_element_is_caught(self):
        """An element in the drawing that no description mentions must fail."""
        scene = minimal_scene(extra_part="star tracker")
        result = checks.check_description(minimal_description(), scene)
        self.assertFalse(result["ok"])
        self.assertTrue(any("drawn but not described" in p and "star tracker" in p
                            for p in result["problems"]))

    def test_described_but_undrawn_element_is_caught(self):
        d = minimal_description(antennas=[{"name": "downlink dish", "form": "paraboloid"}])
        result = checks.check_description(d, minimal_scene())
        self.assertFalse(result["ok"])
        self.assertTrue(any("described but not drawn" in p for p in result["problems"]))

    def test_a_declared_omission_is_allowed(self):
        """Removing an unevidenced part is the right fix; recording why keeps a
        later reviewer from re-adding it."""
        d = minimal_description(
            antennas=[{"name": "star tracker", "form": "barrel"}],
            deliberately_omitted=[{"element": "star tracker",
                                   "reason": "not visible in any reference"}])
        result = checks.check_description(d, minimal_scene())
        self.assertTrue(result["ok"], result["problems"])

    def test_untagged_structural_face_is_caught(self):
        scene = minimal_scene()
        scene.box((5, 0, 0), (1, 1, 1), "white")     # outside any part block
        result = checks.check_description(minimal_description(), scene)
        self.assertFalse(result["ok"])
        self.assertTrue(any("no element tag" in p for p in result["problems"]))


class ProjectionCheckTests(unittest.TestCase):
    """MTG-S1's invisible wings and FY-3D's detached dish, as tests."""

    WING = [{"assert": "visible", "element": "solar array", "min_frac": 0.06}]

    def test_visible_wings_pass(self):
        result = checks.check_projection(minimal_scene(), self.WING)
        self.assertTrue(result["ok"], result["problems"])

    def test_hidden_element_is_caught(self):
        """Correct in 3D, invisible on screen: the check runs on the projection."""
        result = checks.check_projection(minimal_scene(hide_wings=True), self.WING)
        self.assertFalse(result["ok"])
        self.assertTrue(any("does not read" in p for p in result["problems"]))

    def test_touching_elements_pass(self):
        scene = minimal_scene(extra_part="downlink dish")
        result = checks.check_projection(
            scene, [{"assert": "touches", "elements": ["downlink dish", "bus"]}])
        self.assertTrue(result["ok"], result["problems"])

    def test_detached_element_is_caught(self):
        scene = kit.Scene(kit.Camera(az=32, el=18))
        with scene.part("bus"):
            scene.box((0, 0, 0), (2.0, 2.0, 2.0), "gold")
        with scene.part("downlink dish"):
            scene.tube((0, 0, 6.0), (0, 0, 6.8), 0.3, "white")   # floating clear
        result = checks.check_projection(
            scene, [{"assert": "touches", "elements": ["downlink dish", "bus"]}])
        self.assertFalse(result["ok"])
        self.assertTrue(any("detached" in p for p in result["problems"]))

    def test_screen_angle_is_checked_on_the_projection(self):
        scene = minimal_scene()
        good = checks.check_projection(scene, [
            {"assert": "screen_angle", "p0": [0, 0, 0], "p1": [0, 0, 5],
             "expect_deg": 90, "tol_deg": 8}])
        self.assertTrue(good["ok"], good["problems"])
        bad = checks.check_projection(scene, [
            {"assert": "screen_angle", "p0": [0, 0, 0], "p1": [0, 0, 5],
             "expect_deg": 0, "tol_deg": 8}])
        self.assertFalse(bad["ok"])

    def test_missing_element_is_reported_not_skipped(self):
        result = checks.check_projection(
            minimal_scene(), [{"assert": "visible", "element": "nonexistent"}])
        self.assertFalse(result["ok"])


class IconDerivationTests(unittest.TestCase):
    """The icon must come from our own colour SVG, and from nothing else."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_icon_is_the_structural_subset_of_our_own_svg(self):
        scene = minimal_scene()
        colour, icon = self.tmp / "t.svg", self.tmp / "t-icon.svg"
        info = kit.render(scene, colour, icon)
        icon_text = icon.read_text(encoding="utf-8")

        # currentColor, so the portal can recolour it
        self.assertIn("fill:currentColor", icon_text)
        # exactly one path per structural face, and no non-structural detail
        self.assertEqual(icon_text.count("<path"), info["structural_faces"])
        self.assertLess(info["structural_faces"], info["faces"])
        # no palette colour leaks into the mono icon
        for colour_value in kit.PALETTE.values():
            self.assertNotIn(colour_value, icon_text)

    def test_icon_shares_the_colour_svg_viewbox(self):
        """Same fit transform, so icon and artwork can never drift apart."""
        scene = minimal_scene()
        colour, icon = self.tmp / "t.svg", self.tmp / "t-icon.svg"
        kit.render(scene, colour, icon)
        def viewbox(p):
            return p.read_text(encoding="utf-8").split('viewBox="')[1].split('"')[0]
        self.assertEqual(viewbox(colour), viewbox(icon))

    def test_no_raster_can_reach_the_svg(self):
        """The drawing carries no embedded image data by construction."""
        scene = minimal_scene()
        colour, icon = self.tmp / "t.svg", self.tmp / "t-icon.svg"
        kit.render(scene, colour, icon)
        for path in (colour, icon):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("<image", text)
            self.assertNotIn("base64", text)
            self.assertNotIn("xlink:href", text)

    def test_house_palette_stays_within_ten_colours(self):
        info = kit.render(minimal_scene(), self.tmp / "t.svg", self.tmp / "t-icon.svg")
        self.assertLessEqual(len(info["colours"]), 10)
        self.assertGreaterEqual(len(info["colours"]), 3)

    def test_export_signature_matches_the_repo_style(self):
        kit.render(minimal_scene(), self.tmp / "t.svg", self.tmp / "t-icon.svg")
        head = (self.tmp / "t.svg").read_text(encoding="utf-8")[:400]
        self.assertIn('baseProfile="tiny"', head)
        self.assertIn('viewBox="0.00 0.00 512.00', head)


class ApplyRefusalTests(unittest.TestCase):
    """apply_art must refuse anything it cannot justify later."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = self.tmp / "work"
        self.repo = self.tmp / "repo"
        (self.repo / "satellites").mkdir(parents=True)
        (self.repo / "index.json").write_text("[]\n", encoding="utf-8")
        with open(self.repo / "ATTRIBUTIONS.csv", "w", newline="") as fh:
            csv.writer(fh).writerow(
                ["path", "title", "creator_or_rights_holder", "source_url",
                 "original_license_or_terms", "license_url_or_notes"])

    def _candidate(self, folder="testsat", **over):
        base = self.work / folder
        base.mkdir(parents=True, exist_ok=True)
        d = minimal_description(folder, **over)
        (base / "description.json").write_text(json.dumps(d), encoding="utf-8")
        kit.render(minimal_scene(), base / f"{folder}.svg", base / f"{folder}-icon.svg")
        return d

    def test_refuses_a_description_with_no_references(self):
        self._candidate(references=[])
        with self.assertRaises(apply_art.Refused) as ctx:
            apply_art.read_description("testsat", self.work)
        self.assertIn("references", str(ctx.exception))

    def test_refuses_a_description_whose_references_are_repo_paths(self):
        self._candidate(references=[{"n": 1, "source_page": "satellites/testsat/x.jpg",
                                     "downloaded": True, "used_for_geometry": True}])
        with self.assertRaises(apply_art.Refused):
            apply_art.read_description("testsat", self.work)

    def test_refuses_a_missing_description(self):
        with self.assertRaises(apply_art.Refused):
            apply_art.read_description("nosuch", self.work)

    def test_applies_a_good_candidate(self):
        self._candidate()
        index, attrib = [], {}
        actions = apply_art.apply_one("testsat", {"decision": "approve"}, index,
                                      attrib, repo=self.repo, workdir=self.work)
        self.assertTrue(actions)
        entry = index[0]
        self.assertEqual(entry["folder"], "testsat")
        self.assertEqual(entry["artStatus"], "house-generated")
        self.assertEqual(entry["references"], ["https://example.org/spacecraft"])
        self.assertEqual(entry["SVGColourPath"], "satellites/testsat/testsat.svg")
        self.assertTrue((self.repo / "satellites/testsat/testsat.svg").exists())
        self.assertTrue((self.repo / "satellites/testsat/testsat-icon.svg").exists())
        # paperwork: our own work, CC BY 4.0, with the method recorded
        row = attrib["satellites/testsat/testsat.svg"]
        self.assertEqual(row[2], "repo maintainers")
        self.assertEqual(row[4], "CC BY 4.0")
        self.assertIn("never traced", row[5])

    def test_new_folder_is_svg_fallback_not_pending_a_photo(self):
        """This lane exists because no photo can be licensed, so a folder it
        creates must not claim one is on the way."""
        self._candidate()
        index, attrib = [], {}
        apply_art.apply_one("testsat", {"decision": "approve"}, index, attrib,
                            repo=self.repo, workdir=self.work)
        self.assertEqual(index[0]["imageStatus"], "svg-fallback")
        self.assertEqual(index[0]["imageSourceTier"], "")

    def test_existing_photo_fields_are_not_clobbered(self):
        """Adding an icon to an ESA folder must leave its photo paperwork alone."""
        self._candidate()
        index = [{"folder": "testsat", "missionID": "", "missionName": "",
                  "SVGColourPath": "", "SVGBlackPath": "", "PNG1024Path": "",
                  "PNG512Path": "", "imageSourceURL": "https://esa.int/x",
                  "imageRightsHolder": "ESA", "imageLicense": "ESA Standard Licence",
                  "imageCredit": "ESA", "imageSourceTier": "B",
                  "imageStatus": "licensed",
                  "PhotoPath": "satellites/testsat/testsat-photo.jpg"}]
        apply_art.apply_one("testsat", {"decision": "approve"}, index, {},
                            repo=self.repo, workdir=self.work)
        self.assertEqual(index[0]["imageStatus"], "licensed")
        self.assertEqual(index[0]["imageLicense"], "ESA Standard Licence")
        self.assertEqual(index[0]["PhotoPath"], "satellites/testsat/testsat-photo.jpg")
        self.assertEqual(index[0]["artStatus"], "house-generated")

    def test_dropped_icon_is_not_copied_or_recorded(self):
        self._candidate()
        index, attrib = [], {}
        apply_art.apply_one("testsat", {"decision": "approve", "icon": "drop"},
                            index, attrib, repo=self.repo, workdir=self.work)
        self.assertEqual(index[0]["SVGBlackPath"], "")
        self.assertFalse((self.repo / "satellites/testsat/testsat-icon.svg").exists())
        self.assertNotIn("satellites/testsat/testsat-icon.svg", attrib)

    def test_no_reference_image_is_ever_copied_into_the_repo(self):
        self._candidate()
        refs = self.work / "testsat" / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        (refs / "ref1.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 64)
        index, attrib = [], {}
        apply_art.apply_one("testsat", {"decision": "approve"}, index, attrib,
                            repo=self.repo, workdir=self.work)
        written = sorted(p.name for p in (self.repo / "satellites/testsat").iterdir())
        self.assertEqual(written, ["testsat-icon.svg", "testsat.svg"])


class FolderNameGuardTests(unittest.TestCase):
    """The shared guard in index_utils is a filesystem boundary; apply_art must
    go through it rather than around it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_path_like_folder_is_refused_before_any_write(self):
        for bad in ("../escape", "a/b", ".", "..", "Terra", "with_underscore", ""):
            with self.subTest(folder=bad):
                with self.assertRaises((UnsafeFolderName, apply_art.Refused)):
                    apply_art.apply_one(bad, {"decision": "approve"}, [], {},
                                        repo=self.tmp, workdir=self.tmp)
                self.assertFalse((self.tmp / "satellites").exists(),
                                 "a refused folder must not create directories")


class CheckIndexTests(unittest.TestCase):
    """The committed index must satisfy the lane's new invariants."""

    def test_repo_index_passes(self):
        import subprocess
        result = subprocess.run([sys.executable, str(REPO / "tools" / "check_index.py")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_house_generated_entry_needs_references(self):
        import check_index
        entry = {"folder": "testsat", "artStatus": "house-generated",
                 "SVGColourPath": "satellites/testsat/testsat.svg", "missionID": ""}
        self.assertIn("house-generated", json.dumps(entry))
        # the enum and the requirement both live in check_index
        self.assertIn("house-generated", check_index.ART_STATUS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
