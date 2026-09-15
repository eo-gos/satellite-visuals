#!/usr/bin/env python3
"""Apply approved house artwork: copy the SVGs in, write the paperwork.

    python3 tools/apply_art.py ~/Downloads/art-picks.json
    cd tools && npm install && node render_pngs.mjs     # PNG renders
    python3 tools/check_index.py
    git diff                                            # then branch, commit, PR

For each approved pick this:

  0. checks the pick against the candidate: its `candidate` fingerprint (colour
     SVG + icon SVG + description.json, stamped by the checker) must equal the
     working directory's now, so an approval never applies a regenerated
     drawing; and where the 16 px check says the icon breaks up (or there is no
     render to check) the pick must say `icon: keep` or `icon: drop`;
  1. copies `<folder>.svg` and `<folder>-icon.svg` out of the gitignored working
     directory into `satellites/<folder>/` (an icon marked `drop` is not copied,
     and a house-artwork icon a previous apply put there is removed along with
     its ATTRIBUTIONS row — any other icon in that slot is left alone and the
     drop refused);
  2. derives the greyscale twin `satellites/<folder>/grey/<folder>-grey.svg`
     from the copied colour SVG (`tools/desaturate_svg.py`, the same derivation
     every house drawing gets) — the twin is the form the Explorer shows, and
     `check_index.py` refuses a colour SVG without a fresh one;
  3. creates or updates the index.json entry: `folder`, the artwork paths
     (colour, icon, grey), `artStatus: house-generated`, and `references` — the
     list of URLs the description was written from;
  4. adds ATTRIBUTIONS.csv rows for each SVG: repo maintainers, CC BY 4.0, with
     a method note recording that it is an original depiction drawn from
     reference imagery rather than traced from it. The grey twin is a mechanical
     derivative of the colour SVG and needs no row of its own.

**Reference images are never copied into the repository.** Only their URLs
travel, and a folder whose description carries none is refused: an original
depiction with no record of what was looked at cannot be reviewed, and the
`references` list is what makes golden rule 6 auditable after the fact.

PNG renders (colour and grey, plus the grey provenance sidecar) are deliberately
NOT produced here. `render_pngs.mjs` is the one place that turns our SVGs into
the committed rasters, and it runs over the whole tree; this tool prints the
command rather than duplicating it.
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desaturate_svg import write_twin  # noqa: E402
from house_art import checks as art_checks  # noqa: E402
from house_art import schema  # noqa: E402
from house_art.refs import OUT  # noqa: E402
from index_utils import (UnsafeFolderName, by_folder, check_folder_name,  # noqa: E402
                         ensure_entry, load_index, save_index)

REPO = Path(__file__).resolve().parent.parent

ART_STATUS = "house-generated"
ART_LICENCE = "CC BY 4.0"
ART_HOLDER = "repo maintainers"
ART_SOURCE = "https://github.com/eo-gos/satellite-visuals"
METHOD_NOTE = ("original depiction drawn from a structured description via "
               "tools/house_art (golden rule 6); reference imagery consulted, "
               "never traced, and not stored in this repository")


class Refused(Exception):
    """A pick that must not be applied."""


ICON_CHOICES = ("keep", "drop")


def icon_call_required(base, folder):
    """Does this candidate need an explicit icon keep/drop from the reviewer?

    Derived from the candidate itself, never trusted from the pick: the 16 px
    legibility check on `<folder>-icon-render.png`. A candidate with an icon
    SVG but no render to check cannot be judged, so it needs the call too. No
    icon SVG at all: nothing to decide.
    """
    base = Path(base)
    if not (base / f"{folder}-icon.svg").is_file():
        return False
    png = base / f"{folder}-icon-render.png"
    if not png.is_file():
        return True
    return not art_checks.icon_legibility(png)["legible"]


def _is_managed_icon_row(row):
    return (row is not None and len(row) >= 6 and row[2] == ART_HOLDER
            and "silhouette derived from" in row[5])


def load_picks(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    picks = payload.get("picks", payload if isinstance(payload, list) else [])
    return [p for p in picks if p.get("decision") == "approve"]


def read_description(folder, workdir=None):
    base = Path(workdir or OUT) / folder
    path = base / "description.json"
    if not path.exists():
        raise Refused(f"{folder}: no description.json in {base}")
    d = json.loads(path.read_text(encoding="utf-8"))
    problems = schema.validate(d, folder)
    if problems:
        raise Refused(f"{folder}: description invalid — {'; '.join(problems)}")
    urls = schema.reference_urls(d)
    if not urls:
        raise Refused(f"{folder}: description carries no reference URLs — an "
                      f"original depiction must record what was looked at")
    return d, urls


def apply_one(folder, pick, index, attrib_rows, repo=REPO, workdir=None, dry_run=False):
    """Returns a list of human-readable actions. Raises Refused to skip."""
    folder = check_folder_name(folder)
    d, urls = read_description(folder, workdir)

    base = Path(workdir or OUT) / folder
    colour_src = base / f"{folder}.svg"
    icon_src = base / f"{folder}-icon.svg"
    if not colour_src.exists():
        raise Refused(f"{folder}: no {folder}.svg in {base}")

    # The approval is bound to the candidate that was reviewed: the pick must
    # carry the fingerprint the checker stamped, and it must match what is in
    # the working directory now. A regenerated drawing gets a new review.
    expected = schema.candidate_fingerprint(base)
    got = pick.get("candidate")
    if not isinstance(got, str) or not got:
        raise Refused(f"{folder}: pick carries no candidate fingerprint — export it "
                      f"from the checker again (old export format?)")
    if got != expected:
        raise Refused(f"{folder}: pick was reviewed against a different candidate "
                      f"({got[:12]}… vs {expected[:12]}… now in {base}) — the drawing "
                      f"or description changed since review; re-review it")

    # Icon: an explicit keep/drop is required where the 16 px check says the
    # silhouette does not survive (or cannot be checked); a legible icon may be
    # left undecided and is kept. Any value outside keep/drop is refused.
    icon_choice = pick.get("icon")
    if icon_choice is not None and icon_choice not in ICON_CHOICES:
        raise Refused(f"{folder}: icon decision must be one of {ICON_CHOICES}, "
                      f"found {icon_choice!r}")
    if icon_choice is None and icon_call_required(base, folder):
        raise Refused(f"{folder}: the icon needs an explicit keep/drop (it breaks up "
                      f"at 16 px, or has no render to check) and the pick carries none")
    keep_icon = icon_choice != "drop" and icon_src.exists()
    dest = Path(repo) / "satellites" / folder
    colour_rel = f"satellites/{folder}/{folder}.svg"
    icon_rel = f"satellites/{folder}/{folder}-icon.svg"

    # An explicit drop also retires an icon a previous apply of THIS lane put
    # there: the API discovers icons by glob, so an index field alone does not
    # stop it being served. Only a house-artwork icon (its ATTRIBUTIONS row
    # says so) is removed; anything else in that slot is not this lane's to
    # delete and the drop is refused rather than acted on.
    retire_icon = False
    if icon_choice == "drop" and (dest / f"{folder}-icon.svg").is_file():
        if _is_managed_icon_row(attrib_rows.get(icon_rel)):
            retire_icon = True
        else:
            raise Refused(f"{folder}: icon: drop, but the existing {icon_rel} is not a "
                          f"house-artwork icon of this lane (no matching ATTRIBUTIONS "
                          f"row) — removing it is a separate, gated decision")

    entry, created = ensure_entry(index, folder,
                                  str(d.get("mission_id") or ""),
                                  d.get("mission") or "")
    actions = []
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(colour_src, dest / colour_src.name)
        if keep_icon:
            shutil.copyfile(icon_src, dest / icon_src.name)
        elif retire_icon:
            (dest / f"{folder}-icon.svg").unlink()
    if retire_icon:
        attrib_rows.pop(icon_rel, None)

    entry["SVGColourPath"] = colour_rel
    entry["SVGBlackPath"] = icon_rel if keep_icon else ""
    # render_pngs.mjs writes these; record the paths it will produce so the
    # entry is complete the moment that command has run.
    entry["PNG1024Path"] = f"satellites/{folder}/{folder}-1024px.png"
    entry["PNG512Path"] = f"satellites/{folder}/{folder}-512px.png"
    # The greyscale twin is derived here, from the copied colour SVG, so the
    # folder is complete for check_index the moment the PNGs are rendered.
    # write_twin also returns the three grey path fields.
    if not dry_run:
        entry.update(write_twin(entry, Path(repo)))
    else:
        entry.update({"SVGGreyPath": f"satellites/{folder}/grey/{folder}-grey.svg",
                      "PNGGrey1024Path": f"satellites/{folder}/grey/{folder}-grey-1024px.png",
                      "PNGGrey512Path": f"satellites/{folder}/grey/{folder}-grey-512px.png"})
    entry["artStatus"] = ART_STATUS
    entry["references"] = urls
    entry.setdefault("PhotoPath", "")
    # A folder created by THIS lane exists because a licensed photo could not be
    # obtained, so it must not inherit the photo lane's "a photo is coming"
    # default. A folder that already has a photo (the ESA icon case) keeps its
    # photo fields untouched: this lane only ever adds artwork to those.
    if created and not entry.get("PhotoPath"):
        entry["imageStatus"] = "svg-fallback"
        entry["imageSourceTier"] = ""

    rows = [[colour_rel, f"{d.get('mission', folder)} (house artwork)", ART_HOLDER,
             ART_SOURCE, ART_LICENCE, METHOD_NOTE]]
    if keep_icon:
        rows.append([icon_rel, f"{d.get('mission', folder)} icon (house artwork)",
                     ART_HOLDER, ART_SOURCE, ART_LICENCE,
                     f"{METHOD_NOTE}; silhouette derived from {folder}.svg"])
    for row in rows:
        existing = attrib_rows.get(row[0])
        if existing is not None:
            existing[:] = row
        else:
            attrib_rows[row[0]] = row

    actions.append(f"{'NEW ' if created else 'OK  '} {folder}: {colour_rel}"
                   + (f" + icon" if keep_icon else
                      " (icon dropped; previous house icon removed)" if retire_icon
                      else " (icon dropped)") + " + grey twin"
                   + f", {len(urls)} reference URL(s), evidence {d.get('evidence')}")
    return actions


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("picks", help="art-picks.json exported from the checker")
    ap.add_argument("--workdir", default=None,
                    help=f"candidate directory (default {OUT})")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    picks = load_picks(args.picks)
    if not picks:
        print("no approved picks in that file")
        return 0

    index = load_index(REPO)
    rows = list(csv.reader(open(REPO / "ATTRIBUTIONS.csv")))
    header, body = rows[0], rows[1:]
    attrib_rows = {r[0]: r for r in body}
    before = set(by_folder(index))

    applied, refused = 0, 0
    for pick in picks:
        folder = pick.get("folder", "")
        try:
            for line in apply_one(folder, pick, index, attrib_rows,
                                  workdir=args.workdir, dry_run=args.dry_run):
                print(line)
            applied += 1
        except (Refused, UnsafeFolderName) as exc:
            print(f"REFUSED {exc}")
            refused += 1

    if args.dry_run:
        print(f"\ndry run: {applied} would apply, {refused} refused; nothing written")
        return 1 if refused else 0

    # A folder created by this run but refused before it got artwork must not be
    # persisted: an entry with no SVG and no rows reads as covered when it is not.
    keep = {f for f in by_folder(index) if by_folder(index)[f].get("SVGColourPath")}
    index[:] = [e for e in index
                if e.get("folder") in before or e.get("folder") in keep]

    save_index(index, REPO)
    merged = sorted(attrib_rows.values(), key=lambda r: r[0])
    with open(REPO / "ATTRIBUTIONS.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(merged)

    print(f"\n{applied} folder(s) applied"
          + (f", {refused} refused" if refused else "")
          + ".\nNext: cd tools && npm install && node render_pngs.mjs"
          + "\n      python3 tools/check_index.py"
          + "\n      git diff  — then branch, commit, PR.")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
