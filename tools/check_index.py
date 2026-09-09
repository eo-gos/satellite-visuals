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
        print(f"OK   {len(entries)} entries; folders unique and consistent, "
              f"notice conditions consistent")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
