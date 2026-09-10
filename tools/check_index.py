#!/usr/bin/env python3
"""Validate index.json structural + licence-condition invariants (run at PR review).

Two families of check.

**Identity.** Every entry carries an explicit `folder` — the directory under
`satellites/` that holds its files. Before the photo-only lane the folder was
implied by `SVGColourPath`, which stops working the moment a folder has a
licensed photo and no SVG: the path fields are then empty and there is nothing
to derive from. `folder` is now the identity, and the path fields are optional
content.

**Licence conditions.** The ESA Standard Licence grant
(docs/permissions/esa-20260819-0333.md) is conditional: every ESA image must be
marked as available only under that licence, linking ESA's copyright-notice
page. The field carrying that mark is `licenceNoticeUrl` — this check makes the
condition structural instead of a convention a future batch could silently drop.

    python3 tools/check_index.py          # exit 0 clean, 1 with findings

Checks:
  - every entry has a non-empty `folder`, lowercase, and unique across the file;
  - `folder` matches the directory component of every non-empty path field, so
    an entry can never point at another folder's files;
  - `missionID` is a run of digits or "" (blank = not yet mapped, issue #99);
  - `artStatus`, when present, is one of the known values, and a
    `house-generated` entry carries both a colour SVG and a non-empty
    `references` list of URLs — a generated drawing without the record of what
    was looked at cannot be reviewed against golden rule 6;
  - `references` are URLs and never repo paths: reference imagery is consulted,
    never stored (see "House artwork lane" in TASKING.md);
  - every entry with imageLicense "ESA Standard Licence" carries
    licenceNoticeUrl with exactly the required URL;
  - licenceNoticeUrl never appears on a non-ESA entry (it is the marker of a
    rights-holder-imposed display condition, not a general link slot — a new
    licence with its own notice condition must be added here deliberately);
  - any licenceNoticeUrl value is https.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index_utils import SAFE_FOLDER  # noqa: E402  (local sibling module)
from licenses import _norm  # noqa: E402  (local sibling module)

REPO = Path(__file__).resolve().parent.parent

# How a folder's artwork came to exist. Absent means the question has not been
# asked of that entry — the 72 pre-existing hand-drawn SVGs are not retro-labelled.
#   hand-drawn       drawn by a person, the original 72
#   house-generated  written from a structured description by tools/house_art
ART_STATUS = ("hand-drawn", "house-generated")

# licence (normalised) -> the exact notice URL the rights holder requires
NOTICE_REQUIRED = {
    "esa standard licence": "https://www.esa.int/ESA_Multimedia/Copyright_Notice_Images",
}

# Every field whose value is a repo-relative path to one of the entry's files.
PATH_FIELDS = (
    "SVGColourPath", "SVGBlackPath", "PNG1024Path", "PNG512Path",
    "PhotoPath", "PhotoCut512Path", "PhotoCut1024Path",
    "PhotoCleanPath", "PhotoClean512Path", "PhotoClean1024Path",
)


def main():
    entries = json.load(open(REPO / "index.json"))
    problems = []
    seen_folders = {}

    for i, e in enumerate(entries):
        folder = e.get("folder")
        name = folder or e.get("SVGColourPath") or e.get("PhotoPath") or f"<entry {i}>"

        # --- identity -------------------------------------------------------
        if not isinstance(folder, str) or not folder:
            problems.append(f"{name}: missing `folder` — every entry needs one, it is "
                            f"the entry's identity now that path fields may be empty")
        else:
            if not SAFE_FOLDER.match(folder):
                problems.append(f"{folder}: `folder` must be lowercase "
                                f"[a-z0-9][a-z0-9.-]* (naming policy, PR #103)")
            if folder in seen_folders:
                problems.append(f"{folder}: duplicate `folder` (also at entry "
                                f"{seen_folders[folder]}) — folders are unique")
            else:
                seen_folders[folder] = i
            for field in PATH_FIELDS:
                value = e.get(field)
                if not value:
                    continue  # empty is legitimate: photo-only folders have no SVG
                if not isinstance(value, str):
                    problems.append(f"{folder}: {field} is not a string: {value!r}")
                    continue
                parts = value.split("/")
                if len(parts) < 3 or parts[1] != folder:
                    problems.append(f"{folder}: {field} points into another folder: "
                                    f"{value!r}")

        # --- house artwork lane --------------------------------------------
        art_status = e.get("artStatus")
        refs = e.get("references")
        if art_status is not None and art_status not in ART_STATUS:
            problems.append(f"{name}: artStatus must be one of {ART_STATUS}, "
                            f"found {art_status!r}")
        if refs is not None:
            if not isinstance(refs, list) or not refs:
                problems.append(f"{name}: references must be a non-empty list of URLs")
            else:
                for r in refs:
                    if not isinstance(r, str) or not r.startswith(("https://", "http://")):
                        problems.append(f"{name}: references entries must be URLs, "
                                        f"found {r!r} — reference imagery is consulted, "
                                        f"never stored in this repository")
        if art_status == "house-generated":
            if not e.get("SVGColourPath"):
                problems.append(f"{name}: artStatus house-generated needs a "
                                f"SVGColourPath — the drawing is the point of the entry")
            if not refs:
                problems.append(f"{name}: artStatus house-generated needs a non-empty "
                                f"`references` list — an original depiction must record "
                                f"which pages it was drawn from (golden rule 6)")
        if refs and art_status is None:
            problems.append(f"{name}: `references` present without artStatus — set "
                            f"artStatus so the lane is explicit")

        crop = e.get("photoCrop")
        if crop is not None:
            # bool is an int subclass; a JSON true would otherwise read as 1
            ok = (isinstance(crop, list) and len(crop) == 4
                  and all(isinstance(v, int) and not isinstance(v, bool)
                          for v in crop)
                  and crop[2] > 0 and crop[3] > 0
                  and crop[0] >= 0 and crop[1] >= 0)
            if not ok:
                problems.append(f"{name}: photoCrop must be [x, y, w, h] with four "
                                f"non-negative integers and positive w/h, found {crop!r}")

        mission_id = e.get("missionID", "")
        if not (isinstance(mission_id, str) and (mission_id == "" or mission_id.isdigit())):
            problems.append(f"{name}: missionID must be digits or \"\" (blank = "
                            f"unmapped, issue #99), found {mission_id!r}")

        # --- licence conditions ---------------------------------------------
        lic = _norm(e.get("imageLicense", ""))
        notice = e.get("licenceNoticeUrl")
        required = NOTICE_REQUIRED.get(lic)
        if required and notice != required:
            problems.append(f"{name}: imageLicense '{e['imageLicense']}' requires "
                            f"licenceNoticeUrl {required!r}, found {notice!r}")
        if notice and not required:
            problems.append(f"{name}: licenceNoticeUrl present but licence "
                            f"'{e.get('imageLicense', '')}' has no registered notice "
                            f"condition — add it to NOTICE_REQUIRED if intentional")
        if notice and not str(notice).startswith("https://"):
            problems.append(f"{name}: licenceNoticeUrl is not https: {notice!r}")

    for p in problems:
        print(f"FAIL {p}")
    if not problems:
        house = sum(1 for e in entries if e.get("artStatus") == "house-generated")
        print(f"OK   {len(entries)} entries; folders unique and consistent, "
              f"notice conditions consistent, {house} house-generated")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
