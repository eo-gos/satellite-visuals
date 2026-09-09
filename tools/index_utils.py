#!/usr/bin/env python3
"""Shared index.json helpers: identity, loading, and creating a new entry.

`folder` is an entry's identity. It used to be implied by SVGColourPath, which
only worked while every folder had a house SVG; a photo-only folder has empty
path fields and nothing to derive from. `folder_of()` reads the explicit field
and falls back to the old derivation so a tool still works against an index
that predates the migration.

`ensure_entry()` is what the photo-only lane needs from the apply tools: a
folder with a licensed photo and no artwork is a valid folder, so a pick can
create one.
"""

import collections
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Field order for a new entry — matches the existing rows so a migrated file
# and a freshly written one are diff-comparable.
ENTRY_ORDER = (
    "folder", "missionID", "missionName",
    "SVGColourPath", "SVGBlackPath", "PNG1024Path", "PNG512Path",
    "imageSourceURL", "imageRightsHolder", "imageLicense", "imageCredit",
    "imageSourceTier", "imageStatus", "PhotoPath",
)


def folder_of(entry):
    """The entry's folder: the explicit field, else derived from SVGColourPath
    (pre-migration shape). Empty string when neither is available."""
    folder = entry.get("folder")
    if isinstance(folder, str) and folder:
        return folder
    svg = entry.get("SVGColourPath") or ""
    parts = svg.split("/")
    return parts[1] if len(parts) > 2 else ""


def load_index(repo=REPO):
    """index.json as a list of OrderedDicts (key order preserved on rewrite)."""
    return json.loads((Path(repo) / "index.json").read_text(encoding="utf-8"),
                      object_pairs_hook=collections.OrderedDict)


def save_index(index, repo=REPO):
    path = Path(repo) / "index.json"
    path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def by_folder(index):
    return {folder_of(e): e for e in index if folder_of(e)}


def new_entry(folder, mission_id="", mission_name=""):
    """A photo-only entry: identity and mission mapping set, every artwork path
    empty. The photo fields are filled in by whichever apply tool created it."""
    entry = collections.OrderedDict((k, "") for k in ENTRY_ORDER)
    # Strip on write. Mission names come from the CEOS database via the API
    # snapshot and some carry trailing whitespace ("THEMIS "), which would
    # otherwise be baked into index.json and every credit line derived from it.
    entry["folder"] = folder.strip()
    entry["missionID"] = str(mission_id or "").strip()
    entry["missionName"] = (mission_name or "").strip()
    entry["imageSourceTier"] = "A"
    entry["imageStatus"] = "pending-public-domain"
    return entry


def ensure_entry(index, folder, mission_id="", mission_name=""):
    """Return (entry, created). Creates a photo-only entry and inserts it in
    folder order when the folder is new, so the file stays sorted the way the
    existing rows are. Creating the directory on disk is the caller's job — it
    knows whether this is a dry run."""
    existing = by_folder(index)
    if folder in existing:
        return existing[folder], False
    entry = new_entry(folder, mission_id, mission_name)
    position = len(index)
    for i, e in enumerate(index):
        if folder_of(e) > folder:
            position = i
            break
    index.insert(position, entry)
    return entry, True


def parse_new_specs(specs):
    """`--new folder=x missionID=1 missionName=Y` -> {folder: {...}}.

    Each --new takes one folder's key=value pairs; repeat the flag per folder.
    """
    out = {}
    for spec in specs or []:
        fields = {}
        for token in spec:
            if "=" not in token:
                raise ValueError(f"--new expects key=value, got {token!r}")
            key, _, value = token.partition("=")
            fields[key.strip()] = value.strip()
        folder = fields.get("folder")
        if not folder:
            raise ValueError("--new needs folder=<name>")
        out[folder] = {"missionID": fields.get("missionID", ""),
                       "missionName": fields.get("missionName", "")}
    return out
