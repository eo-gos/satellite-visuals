#!/usr/bin/env python3
"""Licence-name -> deed-URL map for the display layer.

`index.json` / `ATTRIBUTIONS.csv` record a human licence *name* (e.g.
"CC BY-SA 3.0") and, in `license_url_or_notes`, the Commons *file page* — not
the licence deed. The portal's credit line needs the deed URL to hyperlink the
licence name ("licence name linked to deed", issue #109). This module is the
single source of that mapping, plus the two obligation predicates the
flow-down table turns on (attribution required? derivatives permitted?).

    from licenses import deed_url, requires_attribution, permits_derivatives
    deed_url("CC BY-SA 2.0 fr")  -> "https://creativecommons.org/licenses/by-sa/2.0/fr/"

Covers every licence string that appears in ATTRIBUTIONS.csv / index.json for
batch 1 (Public domain, CC BY 4.0, CC BY-SA 3.0/4.0, CC BY-SA 2.0 fr) plus the
other open licences the sourcing policy admits (CC0, OGL, further CC versions)
and the non-CC statuses (media-terms, trademark-editorial-use) that have no
generic deed.
"""

import re

# Non-CC licences and public-domain statements: explicit, exact (normalised) keys.
# media-terms / trademark-editorial-use have no generic deed — the source URL
# recorded per file is the operative link, so they map to None on purpose.
LICENSE_DEEDS = {
    "public domain": "https://creativecommons.org/publicdomain/mark/1.0/",
    "public domain (nasa)": "https://creativecommons.org/publicdomain/mark/1.0/",
    "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "ogl": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "ogl v3": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "ogl v3.0": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "media-terms": None,
    "trademark-editorial-use": None,
}

# Generic Creative Commons deeds: cc <flavour> <version> [<jurisdiction port>].
# Matches "CC BY 4.0", "CC BY-SA 3.0", "CC BY-SA 2.0 fr", "CC BY-NC 2.0" (though
# NC/ND never pass the sourcing policy), etc. Jurisdiction ports live at
# .../<flavour>/<version>/<cc>/ on the CC site.
_CC = re.compile(
    r"^cc[ -]?(by(?:[ -]?sa|[ -]?nc(?:[ -]?sa|[ -]?nd)?|[ -]?nd)?)"
    r"[ -]?([0-9]+(?:\.[0-9]+)?)"
    r"(?:[ -]?(igo|[a-z]{2}))?$"
)


def _norm(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def deed_url(name):
    """Return the canonical deed URL for a licence name, or None if there is no
    generic deed (media-terms, trademark editorial use, unknown strings)."""
    key = _norm(name)
    if key in LICENSE_DEEDS:
        return LICENSE_DEEDS[key]
    m = _CC.match(key)
    if m:
        flavour = m.group(1).replace(" ", "-").replace("--", "-")
        version = m.group(2)
        port = m.group(3)
        url = f"https://creativecommons.org/licenses/{flavour}/{version}/"
        if port:
            url += f"{port}/"
        return url
    return None


def requires_attribution(name):
    """True when the licence obliges crediting the rights holder. Only public
    domain / CC0 are exempt (courtesy credit only) — every CC BY*, OGL and
    media-terms case requires it. Unknown strings default to True (safe: the
    portal renders a uniform credit line for every photo regardless)."""
    key = _norm(name)
    if key.startswith("public domain") or key.startswith("cc0"):
        return False
    return True


def permits_derivatives(name):
    """True when the source licence lets us host a cropped / bg-removed cutout.
    ND blocks derivatives; media-terms grants use *as provided* only, so a
    cutout may exceed permission -> gated (issue #109 flow-down table)."""
    key = _norm(name)
    if "nd" in re.split(r"[ -]", key):
        return False
    if key in ("media-terms", "trademark-editorial-use"):
        return False
    return True


if __name__ == "__main__":
    # Self-check against the licence strings that actually appear in batch 1
    # plus the wider admitted set. Prints the resolved deed table.
    samples = [
        "Public domain", "CC0", "CC BY 4.0", "CC BY 3.0", "CC BY-SA 4.0",
        "CC BY-SA 3.0", "CC BY-SA 2.5", "CC BY-SA 2.0", "CC BY-SA 2.0 fr",
        "CC BY-SA 3.0 igo", "OGL v3", "media-terms", "trademark-editorial-use",
    ]
    for s in samples:
        print(f"{s:26} -> {deed_url(s)}  "
              f"(attrib={requires_attribution(s)}, deriv={permits_derivatives(s)})")
