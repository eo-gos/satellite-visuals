#!/usr/bin/env python3
"""Validate index.json licence-condition invariants (run at PR review).

The ESA Standard Licence grant (docs/permissions/esa-20260819-0333.md) is
conditional: every ESA image must be marked as available only under that
licence, linking ESA's copyright-notice page. The field carrying that mark is
`licenceNoticeUrl` — this check makes the condition structural instead of a
convention a future batch could silently drop.

    python3 tools/check_index.py          # exit 0 clean, 1 with findings

Checks:
  - every entry with imageLicense "ESA Standard Licence" carries
    licenceNoticeUrl with exactly the required URL;
  - licenceNoticeUrl never appears on a non-ESA entry (it is the marker of a
    rights-holder-imposed display condition, not a general link slot — a new
    licence with its own notice condition must be added here deliberately);
  - any licenceNoticeUrl value is https.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from licenses import _norm  # noqa: E402  (local sibling module)

REPO = Path(__file__).resolve().parent.parent

# licence (normalised) -> the exact notice URL the rights holder requires
NOTICE_REQUIRED = {
    "esa standard licence": "https://www.esa.int/ESA_Multimedia/Copyright_Notice_Images",
}


def main():
    entries = json.load(open(REPO / "index.json"))
    problems = []
    for e in entries:
        name = e.get("SVGColourPath") or e.get("PhotoPath") or "<unidentified entry>"
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
        print(f"OK   {len(entries)} entries; notice conditions consistent")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
