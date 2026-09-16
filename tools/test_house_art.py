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

import base64
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import apply_art  # noqa: E402
import desaturate_svg  # noqa: E402
import make_art_checker  # noqa: E402
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


class ReflectorRibSortTests(unittest.TestCase):
    """Umbrella reflector ribs must paint behind every gore they overlap on
    screen, whatever the tilt, so the canopy covers them all the way round and
    only the overhang tips show past the rim (George on Biomass, rounds 2-3:
    spars must be consistent through the full 360)."""

    def _violations(self, ribs_behind):
        # reflector tipped towards the camera: the case that put near-side ribs
        # over the canopy. No mast (it is a dark tube too and would be counted).
        scene = kit.Scene(kit.Camera(az=30, el=18))
        scene.ribbed_reflector((0, 0, 0), kit._n((0.15, -0.42, -0.90)), 4.6,
                               ribs=15, sag=0.27, overhang=0.12, scallop=0.09,
                               mast=0.0, ribs_behind=ribs_behind)
        cam = scene.cam
        ordered = sorted(scene.faces,
                         key=lambda f: (sum(cam.depth(p) for p in f.pts) / len(f.pts)) + f.bias)
        def bbox(f):
            xs, ys = zip(*(cam.project(p) for p in f.pts))
            return min(xs), min(ys), max(xs), max(ys)
        def overlap(a, b):
            return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
        ribs = [(i, bbox(f)) for i, f in enumerate(ordered) if f.mat == "dark"]
        gores = [(i, bbox(f)) for i, f in enumerate(ordered) if f.mat == "mesh"]
        self.assertTrue(ribs and gores)
        # a rib face painted AFTER a gore it overlaps on screen would show over it
        return sum(1 for ri, rb in ribs for gi, gb in gores if overlap(rb, gb) and ri > gi)

    def test_ribs_never_paint_over_a_gore_they_overlap(self):
        self.assertEqual(self._violations(ribs_behind=True), 0)

    def test_without_the_bias_ribs_would_paint_over_gores(self):
        self.assertGreater(self._violations(ribs_behind=False), 0)

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

    def _candidate(self, folder="testsat", legible_icon=True, **over):
        base = self.work / folder
        base.mkdir(parents=True, exist_ok=True)
        d = minimal_description(folder, **over)
        (base / "description.json").write_text(json.dumps(d), encoding="utf-8")
        kit.render(minimal_scene(), base / f"{folder}.svg", base / f"{folder}-icon.svg")
        self._icon_render(folder, legible_icon)
        return d

    def _icon_render(self, folder, legible):
        """The 16 px legibility input: one solid blob (legible) or two small
        separated dots (breaks up). The kit's own render is node-side."""
        from PIL import Image
        im = Image.new("L", (64, 64), 255)
        if legible:
            for x in range(8, 56):
                for y in range(8, 56):
                    im.putpixel((x, y), 0)
        else:
            for (x0, y0) in ((6, 6), (48, 48)):
                for x in range(x0, x0 + 10):
                    for y in range(y0, y0 + 10):
                        im.putpixel((x, y), 0)
        im.save(self.work / folder / f"{folder}-icon-render.png")

    def _pick(self, folder="testsat", **over):
        """An approve pick bound to the candidate now in the working dir, the
        way the checker exports it."""
        pick = {"folder": folder, "decision": "approve", "icon": None,
                "candidate": schema.candidate_fingerprint(self.work / folder)}
        pick.update(over)
        return pick

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
        actions = apply_art.apply_one("testsat", self._pick(), index,
                                      attrib, repo=self.repo, workdir=self.work)
        self.assertTrue(actions)
        entry = index[0]
        self.assertEqual(entry["folder"], "testsat")
        self.assertEqual(entry["artStatus"], "house-generated")
        self.assertEqual(entry["references"], ["https://example.org/spacecraft"])
        self.assertEqual(entry["SVGColourPath"], "satellites/testsat/testsat.svg")
        self.assertTrue((self.repo / "satellites/testsat/testsat.svg").exists())
        self.assertTrue((self.repo / "satellites/testsat/testsat-icon.svg").exists())
        # the greyscale twin is derived at apply time, from the copied colour SVG
        self.assertEqual(entry["SVGGreyPath"], "satellites/testsat/grey/testsat-grey.svg")
        self.assertEqual(entry["PNGGrey1024Path"],
                         "satellites/testsat/grey/testsat-grey-1024px.png")
        twin = self.repo / entry["SVGGreyPath"]
        self.assertTrue(twin.exists())
        self.assertEqual(desaturate_svg.chromatic_tokens(twin.read_text(encoding="utf-8")), [])
        src, sha = desaturate_svg.read_stamp(twin.read_text(encoding="utf-8"))
        self.assertEqual(src, "satellites/testsat/testsat.svg")
        self.assertEqual(sha, desaturate_svg.sha256_of(self.repo / src))
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
        apply_art.apply_one("testsat", self._pick(), index, attrib,
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
        apply_art.apply_one("testsat", self._pick(), index, {},
                            repo=self.repo, workdir=self.work)
        self.assertEqual(index[0]["imageStatus"], "licensed")
        self.assertEqual(index[0]["imageLicense"], "ESA Standard Licence")
        self.assertEqual(index[0]["PhotoPath"], "satellites/testsat/testsat-photo.jpg")
        self.assertEqual(index[0]["artStatus"], "house-generated")

    def test_dropped_icon_is_not_copied_or_recorded(self):
        self._candidate()
        index, attrib = [], {}
        apply_art.apply_one("testsat", self._pick(icon="drop"),
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
        apply_art.apply_one("testsat", self._pick(), index, attrib,
                            repo=self.repo, workdir=self.work)
        written = sorted(p.name for p in (self.repo / "satellites/testsat").iterdir())
        self.assertEqual(written, ["grey", "testsat-icon.svg", "testsat.svg"])
        # the grey/ subfolder holds only the derived twin: no raster, no reference
        grey = sorted(p.name for p in (self.repo / "satellites/testsat/grey").iterdir())
        self.assertEqual(grey, ["testsat-grey.svg"])

    # --- approval bound to the reviewed candidate (CX #134 P2) ------------

    def test_pick_without_fingerprint_is_refused(self):
        self._candidate()
        with self.assertRaises(apply_art.Refused) as ctx:
            apply_art.apply_one("testsat", {"decision": "approve"}, [], {},
                                repo=self.repo, workdir=self.work)
        self.assertIn("fingerprint", str(ctx.exception))
        self.assertFalse((self.repo / "satellites/testsat").exists())

    def test_regenerated_candidate_invalidates_the_old_pick(self):
        self._candidate()
        old = self._pick()
        # regenerate under the same folder: a different drawing
        kit.render(minimal_scene(extra_part="antenna"),
                   self.work / "testsat/testsat.svg", self.work / "testsat/testsat-icon.svg")
        with self.assertRaises(apply_art.Refused) as ctx:
            apply_art.apply_one("testsat", old, [], {}, repo=self.repo, workdir=self.work)
        self.assertIn("different candidate", str(ctx.exception))
        self.assertFalse((self.repo / "satellites/testsat/testsat.svg").exists())
        # a fresh export of the regenerated candidate applies
        apply_art.apply_one("testsat", self._pick(), [], {}, repo=self.repo, workdir=self.work)
        self.assertTrue((self.repo / "satellites/testsat/testsat.svg").exists())

    def test_description_edit_invalidates_the_old_pick(self):
        self._candidate()
        old = self._pick()
        d = minimal_description("testsat", distinctive="Now with a dish.")
        (self.work / "testsat/description.json").write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(apply_art.Refused):
            apply_art.apply_one("testsat", old, [], {}, repo=self.repo, workdir=self.work)

    # --- the icon call is explicit where it is needed (CX #134 P2) -------

    def test_flagged_icon_with_no_decision_is_refused(self):
        self._candidate(legible_icon=False)
        with self.assertRaises(apply_art.Refused) as ctx:
            apply_art.apply_one("testsat", self._pick(icon=None), [], {},
                                repo=self.repo, workdir=self.work)
        self.assertIn("explicit keep/drop", str(ctx.exception))
        self.assertFalse((self.repo / "satellites/testsat/testsat-icon.svg").exists())

    def test_flagged_icon_with_explicit_keep_is_copied(self):
        self._candidate(legible_icon=False)
        index = []
        apply_art.apply_one("testsat", self._pick(icon="keep"), index, {},
                            repo=self.repo, workdir=self.work)
        self.assertTrue((self.repo / "satellites/testsat/testsat-icon.svg").exists())
        self.assertEqual(index[0]["SVGBlackPath"], "satellites/testsat/testsat-icon.svg")

    def test_icon_without_a_render_to_check_needs_the_call(self):
        self._candidate()
        (self.work / "testsat/testsat-icon-render.png").unlink()
        with self.assertRaises(apply_art.Refused):
            apply_art.apply_one("testsat", self._pick(icon=None), [], {},
                                repo=self.repo, workdir=self.work)

    def test_legible_icon_may_be_left_undecided_and_is_kept(self):
        self._candidate(legible_icon=True)
        index = []
        apply_art.apply_one("testsat", self._pick(icon=None), index, {},
                            repo=self.repo, workdir=self.work)
        self.assertTrue((self.repo / "satellites/testsat/testsat-icon.svg").exists())

    def test_invalid_icon_value_is_refused(self):
        self._candidate()
        with self.assertRaises(apply_art.Refused):
            apply_art.apply_one("testsat", self._pick(icon="maybe"), [], {},
                                repo=self.repo, workdir=self.work)

    # --- an explicit drop retires the icon this lane put there (CX #134 P2)

    def test_keep_then_drop_removes_the_house_icon_and_its_row(self):
        self._candidate()
        index, attrib = [], {}
        apply_art.apply_one("testsat", self._pick(icon="keep"), index, attrib,
                            repo=self.repo, workdir=self.work)
        icon = self.repo / "satellites/testsat/testsat-icon.svg"
        self.assertTrue(icon.exists())
        self.assertIn("satellites/testsat/testsat-icon.svg", attrib)
        apply_art.apply_one("testsat", self._pick(icon="drop"), index, attrib,
                            repo=self.repo, workdir=self.work)
        self.assertFalse(icon.exists(), "a dropped house icon must not stay on disk")
        self.assertNotIn("satellites/testsat/testsat-icon.svg", attrib)
        self.assertEqual(index[0]["SVGBlackPath"], "")
        # the consumer discovers icons by glob: nothing left for it to find
        self.assertEqual(list((self.repo / "satellites/testsat").glob("*-icon.svg")), [])
        # the colour SVG and the grey twin are untouched by the drop
        self.assertTrue((self.repo / "satellites/testsat/testsat.svg").exists())
        self.assertTrue((self.repo / "satellites/testsat/grey/testsat-grey.svg").exists())

    def test_drop_does_not_remove_an_icon_this_lane_did_not_make(self):
        self._candidate()
        foreign = self.repo / "satellites/testsat/testsat-icon.svg"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("<svg/>", encoding="utf-8")
        attrib = {"satellites/testsat/testsat-icon.svg":
                  ["satellites/testsat/testsat-icon.svg", "traced from a photo",
                   "Some Agency", "https://example.org", "CC BY 4.0", "make_icon.py"]}
        with self.assertRaises(apply_art.Refused) as ctx:
            apply_art.apply_one("testsat", self._pick(icon="drop"), [], attrib,
                                repo=self.repo, workdir=self.work)
        self.assertIn("gated", str(ctx.exception))
        self.assertTrue(foreign.exists())
        self.assertIn("satellites/testsat/testsat-icon.svg", attrib)

    def test_dry_run_drop_deletes_nothing(self):
        self._candidate()
        index, attrib = [], {}
        apply_art.apply_one("testsat", self._pick(icon="keep"), index, attrib,
                            repo=self.repo, workdir=self.work)
        apply_art.apply_one("testsat", self._pick(icon="drop"), index, attrib,
                            repo=self.repo, workdir=self.work, dry_run=True)
        self.assertTrue((self.repo / "satellites/testsat/testsat-icon.svg").exists())


class CheckerRowTests(unittest.TestCase):
    """The review page's icon controls follow the same rule as apply_art's
    requirement: whenever a row needs an icon call, the buttons are there to
    give it (CX #134 pass 2)."""

    ORIG = {"overall": "PASS", "margin_over_control_p95": 0.05,
            "max_edge_overlap": 0.21, "control": {"p95": 0.16},
            "closest_reference": "ref1.jpg"}

    def setUp(self):
        # row_html inlines the candidate's SVGs from the checker's working
        # directory; point it at a temporary one holding a rendered candidate.
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        base = self.tmp / "testsat"
        base.mkdir()
        kit.render(minimal_scene(), base / "testsat.svg", base / "testsat-icon.svg")
        (base / "description.json").write_text(json.dumps(minimal_description()),
                                               encoding="utf-8")
        self._out = make_art_checker.OUT
        make_art_checker.OUT = self.tmp
        self.addCleanup(setattr, make_art_checker, "OUT", self._out)

    def _row(self, icon16, has_icon):
        return make_art_checker.row_html("testsat", minimal_description(), self.ORIG,
                                         {}, icon16, {}, has_icon=has_icon)

    def test_rule_matches_apply_side(self):
        req = make_art_checker.icon_call_required
        self.assertFalse(req(False, None))
        self.assertTrue(req(True, None))
        self.assertTrue(req(True, {"legible": False, "components": 3}))
        self.assertFalse(req(True, {"legible": True, "components": 1}))

    def test_missing_render_shows_both_buttons_and_the_reason(self):
        html = self._row(None, has_icon=True)
        self.assertIn('data-icon-call="1"', html)
        self.assertIn('data-act="keep"', html)
        self.assertIn('data-act="drop"', html)
        self.assertIn("No 16&nbsp;px render to check", html)

    def test_illegible_icon_shows_both_buttons(self):
        html = self._row({"legible": False, "components": 3}, has_icon=True)
        self.assertIn('data-icon-call="1"', html)
        self.assertIn('data-act="keep"', html)
        self.assertIn("breaks into 3 pieces", html)

    def test_legible_icon_needs_no_call_and_shows_no_buttons(self):
        html = self._row({"legible": True, "components": 1}, has_icon=True)
        self.assertIn('data-icon-call="0"', html)
        self.assertNotIn('data-act="keep"', html)

    def test_no_icon_needs_no_call(self):
        html = self._row(None, has_icon=False)
        self.assertIn('data-icon-call="0"', html)
        self.assertNotIn('data-act="drop"', html)

    def test_row_carries_the_candidate_fingerprint(self):
        html = self._row(None, has_icon=False)
        self.assertIn('data-candidate="', html)


class NgonPrismTests(unittest.TestCase):
    """A hexagonal drum with side-mounted wings is a real bus shape and a box
    is not a substitute for it (George, batch-2 round 1). `ngon_prism` must be
    a genuine polygon — flat facets, hard edges, correct face count — and
    `facet_normal` must agree with it so a mount lands on a facet."""

    def _scene(self, **kw):
        s = kit.Scene(kit.Camera(az=35, el=20))
        with s.part("bus"):
            s.ngon_prism((0, 0, 0), 1.0, 2.0, **kw)
        return s

    def test_face_count_is_sides_plus_two_caps(self):
        for n in (5, 6, 8):
            with self.subTest(n=n):
                self.assertEqual(len(self._scene(n=n).faces), n + 2)

    def test_caps_can_be_left_open(self):
        self.assertEqual(len(self._scene(n=6, caps=False).faces), 6)

    def test_every_face_is_structural_so_it_reaches_the_icon(self):
        self.assertTrue(all(f.struct for f in self._scene(n=6).faces))

    def test_vertices_lie_on_the_circumradius(self):
        s = self._scene(n=6)
        side = s.faces[0]
        for x, y, z in side.pts:
            self.assertAlmostEqual((x * x + y * y) ** 0.5, 1.0, places=6)
            self.assertAlmostEqual(abs(z), 1.0, places=6)

    def test_axis_selects_the_extrusion_direction(self):
        s = kit.Scene()
        with s.part("bus"):
            s.ngon_prism((0, 0, 0), 1.0, 4.0, n=6, axis="y")
        ys = [p[1] for f in s.faces for p in f.pts]
        self.assertAlmostEqual(max(ys), 2.0, places=6)
        self.assertAlmostEqual(min(ys), -2.0, places=6)

    def test_facets_are_flat(self):
        """A facet must be planar: this is a polygon, not a smoothed cylinder."""
        s = self._scene(n=6)
        for face in s.faces[:6]:
            nrm = kit._normal(face.pts)
            d = [kit._dot(nrm, p) for p in face.pts]
            self.assertAlmostEqual(max(d) - min(d), 0.0, places=6)

    def test_facet_normal_matches_the_facet_it_names(self):
        s = self._scene(n=6)
        for i in range(6):
            with self.subTest(facet=i):
                want = s.facet_normal(n=6, axis="z", index=i)
                got = kit._normal(s.faces[i].pts)
                self.assertGreater(kit._dot(want, got), 0.999)

    def test_phase_rotates_the_profile(self):
        import math
        a = self._scene(n=6).faces[0].pts[0]
        b = self._scene(n=6, phase=math.pi / 6).faces[0].pts[0]
        self.assertGreater(abs(a[0] - b[0]) + abs(a[1] - b[1]), 0.1)

    def test_it_is_not_a_tube(self):
        """`tube` approximates a circle; this keeps the sides it was asked for."""
        s = kit.Scene()
        with s.part("bus"):
            s.tube((0, 0, -1), (0, 0, 1), 1.0, "gold", n=6)
        tube_faces = len(s.faces)
        self.assertEqual(len(self._scene(n=6).faces), tube_faces)
        # same face budget, but the prism's profile is exact: no radius shrink
        self.assertAlmostEqual(
            max((p[0] ** 2 + p[1] ** 2) ** 0.5 for f in self._scene(n=6).faces
                for p in f.pts), 1.0, places=6)

    def test_a_described_hexagonal_bus_passes_the_consistency_check(self):
        s = self._scene(n=6)
        report = checks.check_description(minimal_description(), s)
        self.assertEqual(report["drawn"], ["bus"])
        self.assertNotIn("drawn but not described", " ".join(report["problems"]))


class SilhouetteRowTests(unittest.TestCase):
    """The review target is the SILHOUETTE the Explorer actually shows on a
    mission page with no licensed photograph (George, 2026-09-16): the icon SVG
    masked in the muted text colour at 0.75 opacity, 62% of the plate. The page
    must show that first, on both plates, and must show it from the ICON, not
    from the colour drawing."""

    ORIG = CheckerRowTests.ORIG

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        base = self.tmp / "testsat"
        base.mkdir()
        kit.render(minimal_scene(), base / "testsat.svg", base / "testsat-icon.svg")
        (base / "description.json").write_text(json.dumps(minimal_description()),
                                               encoding="utf-8")
        self._out = make_art_checker.OUT
        make_art_checker.OUT = self.tmp
        self.addCleanup(setattr, make_art_checker, "OUT", self._out)

    def _row(self, icon16=None, has_icon=True, description=None):
        return make_art_checker.row_html("testsat", description or minimal_description(),
                                         self.ORIG, {}, icon16, {}, has_icon=has_icon)

    def test_row_leads_with_both_explorer_plates(self):
        html = self._row()
        self.assertIn('class="silstrip"', html)
        self.assertIn('class="plate dark"', html)
        self.assertIn('class="plate light"', html)
        # and the silhouette strip comes before the reference/description grid
        self.assertLess(html.index('class="silstrip"'), html.index('class="grid"'))

    def test_plate_tokens_match_the_portal(self):
        css = make_art_checker.CSS
        self.assertIn(make_art_checker.PLATE_DARK, css)
        self.assertIn(make_art_checker.PLATE_LIGHT, css)
        self.assertIn(make_art_checker.PLATE_MUTED, css)
        self.assertIn(f"width:{make_art_checker.PLATE_MARK_PCT}%", css)
        self.assertIn("opacity:.75", css)
        # no placeholder survived the substitution
        self.assertNotIn("__PLATE", css)
        self.assertNotIn("__MARK", css)

    def test_silhouette_is_the_icon_not_the_colour_drawing(self):
        """The mask must come from <folder>-icon.svg. It is currentColor-filled,
        so the plate can tint it; the colour master never is."""
        html = self._row()
        mark = html.split('class="mark"', 1)[1].split("</div>", 1)[0]
        self.assertIn("fill:currentColor", mark)
        self.assertNotIn(kit.PALETTE["panel_m"], mark)

    def test_grey_twin_and_colour_master_are_both_present(self):
        html = self._row()
        self.assertIn("grey twin", html)
        self.assertIn("colour master", html)
        # the grey twin is desaturated, the master is not
        twin = html.split("grey twin", 1)[0]
        self.assertNotIn(kit.PALETTE["panel_m"], twin.rsplit('class="artbox"', 1)[-1])

    def test_sixteen_px_cell_says_when_the_icon_breaks_up(self):
        self.assertIn("breaks into 3", self._row({"legible": False, "components": 3}))
        self.assertNotIn("breaks into", self._row({"legible": True, "components": 1}))

    def test_missing_icon_render_is_stated_on_the_row(self):
        """No render to check is exactly the case that forces an icon call, so
        the cell must say so rather than showing nothing."""
        html = self._row(None, has_icon=True)
        self.assertIn("no render", html)
        self.assertIn('data-icon-call="1"', html)

    def test_a_row_without_an_icon_says_so_instead_of_faking_a_plate(self):
        html = self._row(None, has_icon=False)
        self.assertIn("no icon", html)
        self.assertNotIn('class="plate dark"', html)

    def test_reference_caveat_is_shown_when_present(self):
        d = minimal_description(reference_caveat="bus inferred from a sibling")
        self.assertIn("bus inferred from a sibling", self._row(description=d))

    def test_controls_and_export_contract_are_unchanged(self):
        html = self._row({"legible": False, "components": 3})
        for token in ('data-act="approve"', 'data-act="regenerate"', 'data-act="reject"',
                      'data-act="keep"', 'data-act="drop"', 'data-candidate="',
                      'data-icon-call="1"', 'class="guide"'):
            self.assertIn(token, html)
        self.assertIn("satellite-visuals/house-art-review/2", make_art_checker.SCRIPT)


class IconSixteenPxTests(unittest.TestCase):
    """The 16 px cell must show the raster the legibility call was made on.

    CX #144 pass 1: the cell embedded a 256 px JPEG and let the browser scale it
    to 16 px and to 128 px, so the "magnified" view kept detail the real
    downsample destroys, and both boxes were forced square — gaofen-2's icon is
    256x106. A reviewer was deciding against a picture that had never been
    rendered. These tests decode the embedded raster rather than trusting the
    HTML labels."""

    ORIG = CheckerRowTests.ORIG
    SRC = (256, 106)          # deliberately non-square, gaofen-2's real shape

    def setUp(self):
        from PIL import Image, ImageDraw
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.base = self.tmp / "testsat"
        self.base.mkdir()
        kit.render(minimal_scene(), self.base / "testsat.svg",
                   self.base / "testsat-icon.svg")
        (self.base / "description.json").write_text(json.dumps(minimal_description()),
                                                    encoding="utf-8")
        # a transparent-background icon render, the way render_svg produces one
        im = Image.new("RGBA", self.SRC, (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        dr.rectangle([90, 10, 165, 95], fill=(0, 0, 0, 255))
        dr.rectangle([0, 40, 256, 62], fill=(0, 0, 0, 255))
        self.render = self.base / "testsat-icon-render.png"
        im.save(self.render)
        self._out = make_art_checker.OUT
        make_art_checker.OUT = self.tmp
        self.addCleanup(setattr, make_art_checker, "OUT", self._out)

    def _imgs(self):
        """(src, width attr, height attr) for the px16 and px16big images."""
        html = make_art_checker.row_html(
            "testsat", minimal_description(), self.ORIG, {},
            checks.icon_legibility(self.render), {}, has_icon=True)
        out = {}
        for cls in ("px16", "px16big"):
            m = re.search(r'<img class="%s" src="([^"]+)" width="(\d+)" height="(\d+)"' % cls,
                          html)
            self.assertIsNotNone(m, f"no {cls} image in the row")
            out[cls] = (m.group(1), int(m.group(2)), int(m.group(3)))
        return html, out

    @staticmethod
    def _decode(src):
        from PIL import Image
        head, b64 = src.split(",", 1)
        return head, Image.open(io.BytesIO(base64.b64decode(b64)))

    def test_embedded_raster_is_the_real_16px_thumbnail(self):
        _, imgs = self._imgs()
        head, im = self._decode(imgs["px16"][0])
        self.assertTrue(head.startswith("data:image/png"), head)
        want = checks.icon_thumbnail(self.render, 16)
        self.assertEqual(im.size, want.size)
        self.assertEqual(max(im.size), 16)

    def test_embedded_pixels_equal_the_pixels_that_were_measured(self):
        """Not merely the same dimensions: the same image, losslessly."""
        _, imgs = self._imgs()
        _, im = self._decode(imgs["px16"][0])
        want = checks.icon_thumbnail(self.render, 16)
        self.assertEqual(list(im.convert("L").getdata()), list(want.getdata()))

    def test_aspect_is_preserved_and_not_forced_square(self):
        _, imgs = self._imgs()
        _, im = self._decode(imgs["px16"][0])
        self.assertNotEqual(im.width, im.height, "a 256x106 icon must not come out square")
        src_aspect = self.SRC[0] / self.SRC[1]
        self.assertLess(abs(im.width / im.height - src_aspect), 0.35)
        # and the HTML must not re-impose a square through its attributes
        self.assertEqual((imgs["px16"][1], imgs["px16"][2]), im.size)

    def test_magnification_is_of_that_same_raster(self):
        _, imgs = self._imgs()
        self.assertEqual(imgs["px16"][0], imgs["px16big"][0],
                         "the enlarged view must be the 16 px raster, not a bigger one")

    def test_magnification_is_an_integer_factor(self):
        """A non-integer scale resamples, which is the thing being avoided."""
        _, imgs = self._imgs()
        z = make_art_checker.ICON_ZOOM
        self.assertEqual(imgs["px16big"][1], imgs["px16"][1] * z)
        self.assertEqual(imgs["px16big"][2], imgs["px16"][2] * z)
        self.assertEqual(z, int(z))

    def test_css_does_not_force_a_square_box_on_the_16px_images(self):
        css = make_art_checker.CSS
        self.assertNotIn("img.px16,.px16{width:16px;height:16px", css)
        self.assertNotIn("img.px16big,.px16big{width:128px;height:128px", css)
        self.assertIn("img.px16big{image-rendering:pixelated}", css)

    def test_the_caption_states_the_real_pixel_size(self):
        html, imgs = self._imgs()
        w, h = imgs["px16"][1], imgs["px16"][2]
        self.assertIn(f"actual {w}&times;{h}", html)

    def test_a_missing_render_still_falls_back_and_forces_the_icon_call(self):
        self.render.unlink()
        html = make_art_checker.row_html("testsat", minimal_description(), self.ORIG,
                                         {}, None, {}, has_icon=True)
        self.assertIn("no render", html)
        self.assertIn('data-icon-call="1"', html)
        self.assertNotIn('<img class="px16"', html)


class ComparisonStripTests(unittest.TestCase):
    """A re-review needs last round's silhouette, this round's, the note that
    was written on it and the reference it named, all on the row. Without that a
    reviewer is opening three windows and a file browser to answer one question
    (George, batch-2 round 1)."""

    ORIG = CheckerRowTests.ORIG

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.base = self.tmp / "testsat"
        self.base.mkdir()
        kit.render(minimal_scene(), self.base / "testsat.svg",
                   self.base / "testsat-icon.svg")
        (self.base / "description.json").write_text(json.dumps(minimal_description()),
                                                    encoding="utf-8")
        self._out = make_art_checker.OUT
        make_art_checker.OUT = self.tmp
        self.addCleanup(setattr, make_art_checker, "OUT", self._out)

    def _round1(self):
        prev = self.base / "round1"
        prev.mkdir(exist_ok=True)
        kit.render(minimal_scene(hide_wings=True), prev / "testsat.svg",
                   prev / "testsat-icon.svg")
        return prev

    def _review(self, **over):
        data = {"round": 2, "previous_decision": "regenerate",
                "guidance": "wings on the wrong side", "named_reference": 1}
        data.update(over)
        (self.base / "review.json").write_text(json.dumps(data), encoding="utf-8")
        return data

    def _row(self, refs_local=None):
        return make_art_checker.row_html("testsat", minimal_description(), self.ORIG,
                                         {}, {"legible": True, "components": 1},
                                         refs_local or {}, has_icon=True)

    def test_no_review_file_means_no_comparison(self):
        self.assertNotIn('class="compare"', self._row())

    def test_guidance_is_quoted_verbatim_on_the_row(self):
        self._review()
        html = self._row()
        self.assertIn('class="compare"', html)
        self.assertIn("wings on the wrong side", html)

    def test_both_rounds_silhouettes_are_shown(self):
        self._round1()
        self._review()
        html = self._row()
        self.assertIn("round 1 silhouette", html)
        self.assertIn("round 2 silhouette", html)

    def test_a_missing_previous_round_degrades_to_this_round_only(self):
        """The record is what it is: no round-1 artwork kept, no round-1 cell,
        and the row must still build rather than raise."""
        self._review()
        html = self._row()
        self.assertNotIn("round 1 silhouette", html)
        self.assertIn("round 2 silhouette", html)

    def test_named_reference_is_shown_when_its_file_is_there(self):
        self._round1()
        self._review(named_reference=1)
        png = self.tmp / "ref1.png"
        kit.render(minimal_scene(), self.tmp / "throwaway.svg", self.tmp / "throwaway-icon.svg")
        from PIL import Image
        Image.new("RGB", (64, 48), (200, 200, 200)).save(png)
        html = self._row(refs_local={1: str(png)})
        self.assertIn("the one the note names", html)
        self.assertIn("reference 1", html)

    def test_named_reference_that_is_not_downloaded_is_skipped(self):
        self._review(named_reference=99)
        self.assertNotIn("the one the note names", self._row())

    def test_a_corrupt_review_file_does_not_break_the_page(self):
        (self.base / "review.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(make_art_checker.review_round(self.base))
        self.assertNotIn('class="compare"', self._row())

    def test_comparison_does_not_disturb_the_export_contract(self):
        self._round1()
        self._review()
        html = self._row()
        for token in ('data-candidate="', 'data-icon-call="0"', 'data-act="approve"'):
            self.assertIn(token, html)


@unittest.skipIf(shutil.which("node") is None, "node not available")
class CheckerLogicTests(unittest.TestCase):
    """The page's decision logic, run under node exactly as shipped (the LOGIC
    block is what the page embeds): legacy saved approvals and approvals made
    on a different candidate never reach an export (CX #134 pass 2)."""

    HARNESS = """
const L = require(process.argv[2]);
const rows = [{folder: "testsat", candidate: "NEW", iconCall: true},
              {folder: "other", candidate: "O1", iconCall: false}];
const out = {};
// legacy state: saved by the /1 checker, no candidate field at all
let st = {testsat: {decision: "approve", icon: "keep", guidance: "nice"}};
out.legacy_reset = L.reconcile(st, rows);
out.legacy_state = JSON.parse(JSON.stringify(st));
out.legacy_export = L.buildPicks(st, rows);
// changed candidate: decided on OLD, the row is now NEW
st = {testsat: {decision: "approve", icon: "drop", candidate: "OLD"}};
out.changed_reset = L.reconcile(st, rows);
out.changed_export = L.buildPicks(st, rows);
// a fresh decision binds to the current candidate; a flagged approve without
// an icon call blocks export; with one it exports the fingerprint
st = {};
L.decide(st, rows[0], "decision", "approve");
out.blocked = L.buildPicks(st, rows);
L.decide(st, rows[0], "icon", "keep");
out.exported = L.buildPicks(st, rows);
// a stale entry with only guidance is untouched
st = {other: {guidance: "later"}};
out.guidance_reset = L.reconcile(st, rows);
out.storage_key = L.STORAGE_KEY;
console.log(JSON.stringify(out));
"""

    def test_logic_under_node(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "logic.js").write_text(make_art_checker.LOGIC, encoding="utf-8")
        (tmp / "harness.js").write_text(self.HARNESS, encoding="utf-8")
        proc = subprocess.run(["node", str(tmp / "harness.js"), str(tmp / "logic.js")],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        # legacy approval is dropped, guidance kept, export is undecided and
        # carries no decision under the new fingerprint
        self.assertEqual(out["legacy_reset"], ["testsat"])
        self.assertEqual(out["legacy_state"]["testsat"],
                         {"guidance": "nice", "stale": True})
        pick = out["legacy_export"]["picks"][0]
        self.assertEqual((pick["decision"], pick["icon"], pick["candidate"]),
                         ("undecided", None, "NEW"))
        # a decision made on another candidate is dropped the same way
        self.assertEqual(out["changed_reset"], ["testsat"])
        self.assertEqual(out["changed_export"]["picks"][0]["decision"], "undecided")
        # export gate and binding
        self.assertEqual(out["blocked"], {"missing": ["testsat"]})
        pick = out["exported"]["picks"][0]
        self.assertEqual((pick["decision"], pick["icon"], pick["icon_call"], pick["candidate"]),
                         ("approve", "keep", True, "NEW"))
        self.assertEqual(out["guidance_reset"], [])
        self.assertTrue(out["storage_key"].endswith("/2"))


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
