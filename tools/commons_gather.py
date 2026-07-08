#!/usr/bin/env python3
"""Gather openly-licensed image candidates from Wikimedia Commons (+ NASA Images).

For every index.json entry whose imageStatus starts with "pending", search
Commons for spacecraft imagery, keep only results that (a) carry a
machine-readable open licence and (b) pass a name-token filter, and write
them to tools/out/candidates.json for human review via make_gallery.py.

Only sources with explicit machine-readable licences are automated —
see ASSET-LICENSING.md. Never add a scraper for arbitrary websites here.

Usage:
    python3 tools/commons_gather.py                  # all pending entries
    python3 tools/commons_gather.py alos-2 goes-16   # specific folders
    python3 tools/commons_gather.py --terms "ESA logo" --key esa-logo
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tools" / "out"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
NASA_API = "https://images-api.nasa.gov/search"
UA = "satellite-visuals-curation/1.0 (https://github.com/eo-gos/satellite-visuals)"

# Licences we accept, matched against Commons extmetadata LicenseShortName.
# The deny-list is checked first: NC/ND variants share the "CC BY" prefix,
# so a prefix allowlist alone would let them through.
DENIED_LICENCE = re.compile(
    r"\b(nc|nd)\b|non[ -]?commercial|no[ -]?deriv|fair use|copyright",
    re.IGNORECASE,
)
OPEN_LICENCE = re.compile(
    r"^(public domain|pd\b|no restrictions|cc0|cc[ -]by(?:[ -]sa)?(?:[ -][0-9.]+)?(?:[ -]igo)?|attribution\b|ogl)",
    re.IGNORECASE,
)


def licence_ok(licence: str) -> bool:
    return bool(licence) and not DENIED_LICENCE.search(licence) and bool(OPEN_LICENCE.search(licence))


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def commons_search(query: str, limit: int = 20) -> list:
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "list": "search",
        "srsearch": query, "srnamespace": 6, "srlimit": limit,
    })
    data = fetch_json(f"{COMMONS_API}?{params}")
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def commons_imageinfo(titles: list) -> list:
    """Return per-file url/thumb/licence/author for openly-licensed files."""
    results = []
    for i in range(0, len(titles), 20):
        params = urllib.parse.urlencode({
            "action": "query", "format": "json",
            "titles": "|".join(titles[i:i + 20]),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size",
            "iiurlwidth": 480,
        })
        data = fetch_json(f"{COMMONS_API}?{params}")
        for page in data.get("query", {}).get("pages", {}).values():
            for info in page.get("imageinfo", []):
                meta = info.get("extmetadata", {})
                licence = meta.get("LicenseShortName", {}).get("value", "")
                if not licence_ok(licence):
                    continue
                artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
                credit = re.sub(r"<[^>]+>", "", meta.get("Credit", {}).get("value", "")).strip()
                results.append({
                    "source": "commons",
                    "title": page.get("title", ""),
                    "url": info.get("url", ""),
                    "thumb": info.get("thumburl", info.get("url", "")),
                    "page": info.get("descriptionurl", ""),
                    "licence": licence,
                    "artist": artist,
                    "credit": credit or artist,
                    "width": info.get("width"),
                    "height": info.get("height"),
                })
    return results


def nasa_search(query: str, limit: int = 10) -> list:
    params = urllib.parse.urlencode({"q": query, "media_type": "image", "page_size": limit})
    try:
        data = fetch_json(f"{NASA_API}?{params}")
    except Exception:
        return []
    out = []
    for item in data.get("collection", {}).get("items", [])[:limit]:
        meta = (item.get("data") or [{}])[0]
        links = item.get("links") or [{}]
        out.append({
            "source": "nasa-images",
            "title": meta.get("title", ""),
            "url": links[0].get("href", ""),
            "thumb": links[0].get("href", ""),
            "page": f"https://images.nasa.gov/details/{meta.get('nasa_id','')}",
            "licence": "Public domain (NASA)",
            "artist": meta.get("secondary_creator", "") or "NASA",
            "credit": meta.get("secondary_creator", "") or "NASA",
        })
    return out


def candidates_for(name: str, extra_terms: list) -> list:
    tokens = [norm(name)]
    queries = extra_terms or [
        f"{name} satellite", f"{name} spacecraft", f"{name} artist impression",
    ]
    titles = []
    for q in queries:
        titles += commons_search(q)
        time.sleep(0.3)
    # de-dup, then require the mission token in the filename unless the
    # caller supplied explicit terms (e.g. logo searches)
    titles = list(dict.fromkeys(titles))
    if not extra_terms:
        titles = [t for t in titles if any(tok and tok in norm(t) for tok in tokens)]
    found = commons_imageinfo(titles)
    found += nasa_search(name if not extra_terms else extra_terms[0])
    if not extra_terms:
        found = [f for f in found if any(tok and tok in norm(f["title"]) for tok in tokens)]
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="*", help="folder names to gather for (default: all pending)")
    ap.add_argument("--terms", help="explicit search terms (skips the mission-name queries + token filter)")
    ap.add_argument("--key", help="output key to file --terms results under")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    out_path = OUT / "candidates.json"
    results = json.load(open(out_path)) if out_path.exists() else {}

    if args.terms:
        key = args.key or norm(args.terms)
        results[key] = {"query": args.terms, "candidates": candidates_for(args.terms, [args.terms])}
        print(f"{key}: {len(results[key]['candidates'])} candidates")
    else:
        index = json.load(open(REPO / "index.json"))
        for entry in index:
            folder = entry["SVGColourPath"].split("/")[1]
            if args.folders and folder not in args.folders:
                continue
            if not args.folders and not entry.get("imageStatus", "").startswith("pending"):
                continue
            name = entry.get("missionName") or folder
            cands = candidates_for(name, [])
            results[folder] = {
                "missionID": entry.get("missionID", ""),
                "missionName": name,
                "candidates": cands,
            }
            print(f"{folder}: {len(cands)} candidates")

    json.dump(results, open(out_path, "w"), indent=2)
    print(f"\nWrote {out_path.relative_to(REPO)} — next: python3 tools/make_gallery.py")


if __name__ == "__main__":
    sys.exit(main())
