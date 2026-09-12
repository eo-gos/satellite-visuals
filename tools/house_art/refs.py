"""Reference gathering for the house-artwork lane.

Two rules, both of them licence rules rather than conveniences:

  1. **Reference images are never stored in the repository.** They are fetched
     into a working directory under `tools/out/`, which is gitignored, so a
     person can look at them while writing the description and while reviewing
     the drawing. Looking at an image is not reuse; hosting it is. Everything
     the repository keeps is the URL.

  2. **Any source may be looked at.** This is the one place in the repo where
     the Commons/agency-only sourcing rule does not apply, because nothing is
     being licensed. `commons_gather.py` is for images we intend to host and is
     correspondingly strict; this is not.

The output is `references.json` in the working directory plus the downloaded
files beside it. `make_art_checker.py` reads both; `apply_art.py` reads only the
URLs, and refuses a folder whose description has none.
"""

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
# Gitignored. Never write a reference image anywhere else.
OUT = REPO / "tools" / "out" / "house_art"

UA = ("Mozilla/5.0 (compatible; eo-gos-satellite-visuals/1.0; "
      "+https://github.com/eo-gos/satellite-visuals)")

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def workdir(folder):
    d = OUT / folder / "refs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get(url, binary=False, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    data = urllib.request.urlopen(req, timeout=timeout).read()
    return data if binary else data.decode("utf-8", "replace")


def commons_search(term, limit=8):
    """Wikimedia Commons image search -> reference candidates (URLs + credit)."""
    api = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {term}", "gsrnamespace": "6",
        "gsrlimit": str(limit), "prop": "imageinfo",
        "iiprop": "url|extmetadata|size", "iiurlwidth": "1400"})
    payload = json.loads(_get(api))
    out = []
    for page in (payload.get("query") or {}).get("pages", {}).values():
        info = page["imageinfo"][0]
        meta = info.get("extmetadata", {})
        licence = (meta.get("LicenseShortName") or {}).get("value", "")
        artist = re.sub("<[^>]+>", "", (meta.get("Artist") or {}).get("value", ""))[:60]
        out.append({"source_page": info.get("descriptionurl"),
                    "image_url": info.get("thumburl") or info.get("url"),
                    "credit": f"{artist} ({licence})".strip(),
                    "title": page["title"]})
    return out


def page_images(page_url, pattern=r'(?:src|href)="([^"]+\.(?:jpg|jpeg|png))"'):
    """Reference candidates linked from an ordinary web page (agency pages,
    Gunter's Space Page, an eoPortal mission page)."""
    html = _get(page_url)
    seen, out = set(), []
    for match in re.finditer(pattern, html, re.I):
        url = urllib.parse.urljoin(page_url, match.group(1))
        if url in seen or re.search(r"logo|icon|avatar|sprite|favicon", url, re.I):
            continue
        seen.add(url)
        out.append({"source_page": page_url, "image_url": url,
                    "credit": urllib.parse.urlparse(page_url).netloc,
                    "title": os.path.basename(urllib.parse.urlparse(url).path)})
    return out


def fetch(folder, candidates, limit=6, min_bytes=4000):
    """Download candidates into the gitignored working directory.

    Returns the reference records to put in `description.json`. Each record
    carries the URLs and a `used_for_geometry` flag the author sets by hand
    after looking: a search hit that turns out to be a different vehicle, or the
    mission's data rather than its hardware, stays in the list marked unused
    rather than being quietly dropped — the review page shows it greyed out.
    """
    directory = workdir(folder)
    kept = []
    for cand in candidates:
        if len(kept) >= limit:
            break
        url = cand.get("image_url")
        if not url:
            continue
        try:
            payload = _get(url, binary=True)
        except Exception:
            continue
        if len(payload) < min_bytes:
            continue
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        if ext not in IMAGE_EXTS:
            ext = ".jpg"
        n = len(kept) + 1
        path = directory / f"ref{n}{ext}"
        path.write_bytes(payload)
        kept.append({"n": n, "source_page": cand.get("source_page"),
                     "image_url": url, "credit": cand.get("credit", ""),
                     "title": cand.get("title", ""),
                     "downloaded": True, "used_for_geometry": True,
                     "_local": str(path)})
    (directory.parent / "references.json").write_text(
        json.dumps(kept, indent=2) + "\n", encoding="utf-8")
    return kept


def text_reference(url, credit="text reference"):
    """A page consulted for its description rather than its pictures."""
    return {"source_page": url, "image_url": None, "credit": credit,
            "downloaded": False, "used_for_geometry": True}


def strip_local(references):
    """The form that goes into description.json: no local paths, ever."""
    return [{k: v for k, v in r.items() if not k.startswith("_")}
            for r in references]


def local_path(reference):
    """Where the checker should read this reference's thumbnail from, or None.

    Lives only in the working copy of references.json, never in the committed
    description.
    """
    return reference.get("_local")
