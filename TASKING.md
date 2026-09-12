# Curation tasking brief

This is the working brief for curating visual assets in this repo. It is written so you can pick it up without any other context. If something here contradicts `ASSET-LICENSING.md`, that file wins.

## What this repo is for

The EO-GOS portal shows a page for every Earth-observation mission (~1,200 and growing). This repo supplies the visuals: a stylised SVG of each satellite (our own artwork), PNG renders of those SVGs, and — where we can get one legally — a real photo or render of the spacecraft. `index.json` maps every folder to its CEOS database mission ID and records the licence of every photo. A second asset class, agency/provider logos, is being added under `agencies/` (issue #101).

## The golden rules

1. **Attribution is not a licence.** Saying where an image came from does not give us permission to host it. An image is usable only if its *owner* has granted an open licence (public domain, CC0, CC BY, CC BY-SA, OGL) or their published media terms permit reuse.
2. **Never source images from Google Images or general web search.** Only from sources that state the licence machine-readably or explicitly: Wikimedia Commons, NASA/NOAA/USGS (US-gov = public domain), agency media pages with stated terms.
3. **Photos must be agency or manufacturer imagery.** Real photos and official 3D renders published by the operating agency, manufacturer, or a space agency's media outlet are in (NASA's "spacecraft model" renders are exactly right). Fan art and community-drawn illustrations are out, even when properly licensed — being on Commons doesn't make something agency imagery. Photos of physical models/mockups (museum or exhibition pieces) are case-by-case: ask George. Also check the file is what its extension says (batch 1 included an SVG mislabelled `.jpg`).
4. **Every photo gets its paperwork before it gets committed:** `imageLicense`, `imageCredit`, `imageSourceURL` in `index.json`, plus a row in `ATTRIBUTIONS.csv`. No exceptions.
5. **Commercial-operator renders (Tier D) are never taken without explicit permission.** The operators (Planet, ICEYE, Umbra, …) are people we work with; a licensing mistake costs trust, not just a takedown. Permission is often easier than it sounds — see the Tier D permission ladder under Task A. When in doubt: leave the SVG as the visual (`imageStatus: svg-fallback`) or ask George.
6. **SVGs must be original depictions, not traces.** Drawing the satellite in our house style (using photos only as reference for what it looks like) is our own copyright. A 1:1 trace of one specific render copies that image's composition and is a derivative — don't do it, and flag any existing SVG that looks like one. This is why a folder never *needs* an SVG: a licensed photo is a better answer than a traced drawing. The one traced asset the repo does allow is the mono silhouette icon, and only from a public-domain or CC photo — see the photo-only lane below.
7. **Logos are never redrawn** — official files only (see Task C).
8. **All work on branches, PR per batch, never commit to `main`.** Keep commit messages plain (no generated-by/co-author trailers).

### ESA images — the standing rules

ESA answered our permission query in writing on 2026-08-19 (reference **ESA HQ PHOTOS 20260819-0333**; full record in `docs/permissions/esa-20260819-0333.md`). That answer sets four rules you must follow whenever a batch touches esa.int:

- **ESA-copyright images are pre-cleared.** Future batches may take them under the ESA Standard Licence with no per-image permission ask — ESA granted blanket permission. Contractor credits (ESA/ATG medialab, ESA–P. Carril, ESA/AOES Medialab, ESA/Mlabspace, ESA/Denmann production) are covered too. The usual paperwork still applies (rule 4).
- **Every ESA entry carries `licenceNoticeUrl` in `index.json`:** `"licenceNoticeUrl": "https://www.esa.int/ESA_Multimedia/Copyright_Notice_Images"`, placed after `imageStatus`. This is ESA's condition of the grant — the credit alone is not enough; the image must also be marked as available *only* under the ESA Standard Licence. It goes in `index.json` only, not in `ATTRIBUTIONS.csv`. Reviewers run `python3 tools/check_index.py`, which fails if the field is missing, wrong, or on a non-ESA entry.
- **Never background-remove an ESA image.** ESA ruled that removing the background "would fundamentally change" the image. Cropping, aspect-ratio changes and resizing are fine; matting is prohibited permanently, and the cutter refuses these photos by design. Instead, look for ESA's **official "clean" version** — many missions have a render on a plain or transparent background in the same multimedia library. Source that as `<folder>-photo-clean.<ext>` with the usual paperwork: source URL, credit copied verbatim, `ATTRIBUTIONS.csv` row.
- **Crop-and-resize display versions are allowed** from a clean original: `<folder>-photo-clean-1024px.png` and `<folder>-photo-clean-512px.png`, mirroring the photo-cut naming. Cropping and scaling only — no matting, no background edits. ESA's ruling permits cropping and aspect-ratio change, so a multi-view render can be cropped down to one view: give the pick a `"crop": [x, y, w, h]` in pixels of the original, or `--crop <folder>=x,y,w,h`. The archival file is stored exactly as published either way.

Finding clean versions for the eleven ESA folders already committed is live curator work (issue #125).

## Task A — satellite photos (the main job)

Goal: every mission folder gets a properly licensed photo/render of the spacecraft, recorded in `index.json` with `imageStatus: licensed`. Where none exists, `imageStatus: svg-fallback` — the SVG is the visual, and that's fine.

**One folder per visual design, not per mission.** The portal's API maps mission variants onto a folder (Sentinel-1A and 1B both use `sentinel-1`; 1C/1D use `sentinel-1c` because they look different). So a photo of *any* visually-identical unit serves the whole series — note which unit it shows in the ATTRIBUTIONS title if known. Only make a new folder when a block/generation genuinely looks different.

### Folder-to-mission mapping and priority

The folder is keyed to the *visual*; mission→folder is an explicit, curated mapping — never inferred from names.

- **One folder per family, by default.** A single family folder (`sentinel-2`) supplies the image for every instance in that family (2A/2B/2C/2D). Only split out a per-instance folder (`sentinel-1c`) when a block genuinely looks different — and then map *only* those instances to it. When a family has one image, every instance uses it; when a folder holds instance-specific artwork, those instances map there.
- **The mapping is authored, not derived.** Which folder covers a mission lives in the API's mission→folder map (`missions.json`) and the `index.json` `missionID`, set by hand. Do **not** infer family membership by stripping the name — names lie: Sentinel-5P is a standalone satellite, not a Sentinel-5 variant; FY-1 and FY-3C are unrelated; Landsat-7 differs from 8/9. A wrong guess puts the wrong picture on a mission page.
- **Don't create variant folders speculatively.** If unsure whether a new unit looks different, use the family folder. One folder until a visual difference forces a second.
- **Priority is coverage-first.** A family with *no* image at all outranks completing a variant set. Get one good image for every family before adding a second visual to any family. When picking a batch, read the pending list as *families needing a first image*, not as individual folders — e.g. do `sentinel-3` (no image yet) before a second Sentinel-2 variant. This follows from the rule above: once the family folder has an image, every instance is already covered, so there is nothing to "complete" unless a variant genuinely differs.

The current folder set predates this policy and needs a one-off cleanup to match it — tracked in issue #117 (`sentinel-2c` folds into `sentinel-2`; `sentinel-1c` stays; blank-`missionID` canonical folders get their mappings authored, overlapping #99). It does not affect in-flight batches.

The workflow (from the repo root):

```bash
# 1. Gather candidates for every entry still pending (or name specific folders)
python3 tools/commons_gather.py

# 2. Build the review gallery and open it in a browser
python3 tools/make_gallery.py
open tools/out/gallery.html
```

**Wide frames: crop before cutting.** Some agencies publish only a wide shot — two
satellites in formation, one small over Earth — where cutting the whole frame leaves
mostly empty space. Give the pick a `"crop": [x, y, w, h]` in pixels of the raw (or
`--crop <folder>=x,y,w,h` on `process_photos.py`) and the cutter works on that box
instead. The raw `-photo.<ext>` is still stored exactly as published; only the cutter's
input is narrowed, and the cutout's `ATTRIBUTIONS.csv` note records the box.
Both lanes validate a box the same way: four real integers, inside the image, and
only an absent key or `null` means "no crop" — a box given as `[]`, `false` or a
string is a curation error and is refused rather than quietly ignored.

3. **Pick.** This is the judgement step a script can't do: most search hits are the satellite's *data* (pretty pictures of Earth), not the satellite. Pick the best image *of the spacecraft* — official renders and pre-launch cleanroom photos both count (golden rule 3: agency/manufacturer imagery only). Between licence-equal candidates, prefer one where the spacecraft is fully in frame against an uncluttered background — after your batch merges, the maintainers derive transparent cutouts from these photos for the portal, and clean subjects cut best. Leave "none of these" selected if nothing shows the spacecraft. Click **Export picks** (downloads `picks.json`).

```bash
# 4. Apply: downloads each pick and writes all the paperwork (one command,
#    both lanes — see "Adding a brand-new folder" below)
python3 tools/apply_clean.py ~/Downloads/picks.json

# 5. Review what changed, then branch/commit/PR
git diff
git checkout -b feat/photos-batch-01
git add -A && git commit -m "Photos batch 1: <folders>"
git push -u origin feat/photos-batch-01   # then open a PR
```

**In the PR description, list each mission and its licence** (batch 1 skipped this — required from batch 2 on). The reviewer checks: is it actually the right satellite, is the licence real (click through to the source page), is the credit sensible.

Batch size: ~20–25 missions per PR (batch 1 landed 22 and reviewed comfortably).

For the ~14 missions Commons can't cover, `image-sourcing-manual-worklist.csv` lists each owner's image library and the licence you're looking for — same paperwork, found by hand. Tier D rows: rule 5 applies, and the ladder below is how permission actually gets obtained.

**After your batch merges (not your job):** the maintainers run `tools/process_photos.py` over the new photos to derive transparent cutouts (`-photo-cut-1024px/-512px.png`) with their own paperwork. Your only lever on that step is picking cuttable images. Anything the cutter can't handle goes on the re-source list — current priorities are in issue #113 (plus ace and sentinel-3 from batch 1, which need proper agency imagery; for Sentinels, ESA's multimedia library publishes some renders under CC BY-SA 3.0 IGO, which qualifies — but note that ESA's CC subset is overwhelmingly *data* imagery, so most spacecraft renders come under the ESA Standard Licence, which is also accepted; see `ASSET-LICENSING.md`). ESA Standard Licence photos are never cut — their display version is ESA's own clean render, per the ESA rules above.

### Tier D — how permission realistically happens

Three routes, tried in order:

**Route 1 — published media terms (your job, do this first).** Many operators run a press/media page whose stated terms already permit use with credit. If the terms are clear, that *is* the permission — no email needed. Record: `imageSourceURL` = the media page, `imageCredit` = the credit they specify, `imageStatus: media-terms`. Verified examples:

- **ICEYE** — [media assets page](https://www.iceye.com/newsroom/media-assets) offers satellite hardware renders and states: *"All photos, images and videos on this page are subject to copyright and should be credited to ICEYE, unless otherwise indicated."* → credit "ICEYE".
- **Capella Space** — [media kit](https://www.capellaspace.com/media-kit) offers **Satellite Renders** and launch photos with explicit per-context rules: print/web = *"Image credit: Capella"*.

Leads to follow up by hand (their terms pages need a browser; scripted checks couldn't confirm):

- **Airbus** — Media Centre (mediacentre.airbus.com); find its conditions-of-use for Pleiades renders.
- **Maxar/Vantor** — formal [Display & Media License](https://vantor.com/resources/display-media-license) with attribution format `[Product] © [YEAR] Maxar Technologies`; confirm whether it covers spacecraft photos or only data imagery. **Caution:** Maxar's Open Data Program is CC BY-**NC** — NC fails our licence rules; don't take it via the automated path.
- **Planet** — press page (planet.com/press) was down when checked; retry.
- **Umbra** — all their *data* is CC BY 4.0 ([open-license commitment](https://umbra.space/open-license)), so Umbra SAR imagery clears cleanly — but their [press kit](https://umbra.space/press-kit/) states no terms for spacecraft renders → route 2.

If the terms are absent, ambiguous, or say "contact us" → escalate to George.

**Route 2 — ask via an existing relationship (George).** For operators we already correspond with (survey counterparties: ICEYE, Umbra, iQPS, Planet, …), George appends a one-paragraph ask to an existing thread: approved render + preferred credit line for the mission page. Operators generally want their spacecraft depicted correctly in a CEOS-facing directory. Your part: prep the target list (operator, mission, proposed image, contact hint).

**Route 3 — cold email to press@ (George, standard template).** Low expectation; the SVG stays in place until an answer arrives, and silence costs nothing.

Record-keeping for routes 2–3: a reply saying "yes, use X with credit Y" is sufficient — note the sender and date in the `ATTRIBUTIONS.csv` notes column and keep the email. No signed paperwork needed.

## Task B — the 12 blank mission IDs (issue #99)

Twelve `index.json` entries have an empty `missionID` because the mapping needs a human call (e.g. the `sentinel-1` folder vs per-satellite A/B/C DB rows; the `ace` folder, whose image is probably the 1997 Advanced Composition Explorer, not missionID 648). Issue #99 has the full list and notes. Resolve each with George — the answer is sometimes "this folder maps to no mission and should be moved to `other-spacecraft/`". Several of these are family-canonical folders whose instance mappings are governed by the folder-to-mission policy above; the cleanup in #117 authors them.

## Task C — agency/provider logos (issue #101)

New asset class under `agencies/<acronym-lowercase>/`, same schema and paperwork as satellites. Differences:

- Logos are **trademarks**: we use them only to identify the agency next to its own missions. The licence bar is different — record `imageStatus: trademark-editorial-use` plus the brand-terms URL when a logo isn't openly licensed but its brand page permits editorial use.
- **Official files only, never redrawn.** SVG preferred.
- Sourcing ladder: (1) Wikimedia Commons — US-gov agency logos are public domain, simple text logos are often `PD-textlogo`; note that logos on *English Wikipedia* (rather than Commons) are usually fair-use and NOT usable. (2) The agency/company's own brand or press page. (3) No logo → the portal shows a text chip, which is fine.
- Priority: the ~35 CEOS member agencies first (ceos.org's member page is the reference for the *current* logo), then commercial providers (ICEYE, Umbra, iQPS, Planet, Capella, SatVu, Airbus…).
- `tools/commons_gather.py --terms "ESA logo" --key esa-logo` reuses the *gather and gallery* steps for logo searches. `apply_picks.py` only handles satellite folders — for logos, download the picked file and do the paperwork (folder, index entry, `ATTRIBUTIONS.csv` row) by hand until a logo-aware apply tool exists.

## The photo-only lane — what makes a valid folder

**A licensed photo or render alone makes a valid folder. No SVG is required.** This is
the current shape of the work: sourcing imagery, not drawing. House colour SVGs are a
separate project for later, and the 72 folders that already have them keep them.

What each asset does:

| Asset | Where it shows | Required? |
|---|---|---|
| licensed photo + its cutout or clean render | the mission page | **yes** — this is the point |
| `<name>-icon.svg` | mission lists, timelines, launch markers | no — lists just omit the icon |
| `<name>.svg` colour vector + its PNG renders | fallback when there is no photo | no |

`index.json` carries an explicit `folder` field on every entry — that is the entry's
identity now that a folder can exist with no SVG to derive it from. The path fields
(`SVGColourPath`, `PNG1024Path`, …) are optional content and may be `""`.
`python3 tools/check_index.py` enforces this: `folder` present, lowercase, unique, and
matching the directory of every non-empty path field.

### Adding a brand-new folder

**There is one apply command.** `apply_clean.py` reads the whole picks file, sends each
pick to its lane — clean renders itself, ordinary photos to `apply_picks.py` — and
creates any folder that does not exist yet:

```bash
python3 tools/apply_clean.py ~/Downloads/picks.json
python3 tools/check_index.py
```

The `new_folders` block that `make_checker.py` exports carries each folder's missionID
and name, so a batch of brand-new folders applies in that one command. For a one-off
without a checker export, the same thing as a flag:

```bash
python3 tools/apply_clean.py ~/Downloads/picks.json \
    --new folder=radarsat-2 missionID=352 missionName=RADARSAT-2
```

`apply_picks.py` is the photo lane's implementation and takes the same arguments, but
call `apply_clean.py` — it is the entry point that knows about both lanes. The entry
lands in folder order with empty artwork paths, and the photo fields are filled from the
pick. `missionID` comes from the CEOS database (George, or the API's mission snapshot);
leave it `""` if unresolved — that is issue #99's queue, not a blocker.

Doing it by hand instead: create `satellites/<name>/` (lowercase, matching the portal's
naming — ask if unsure), add the entry with `folder` set, and add the `ATTRIBUTIONS.csv`
rows. If you *do* draw artwork, `cd tools && npm install && node render_pngs.mjs`
regenerates the PNGs, and the SVGs get maintainer/CC BY 4.0 rows.

### Silhouette icons from photos

Where a folder has a cutout and no icon, `tools/make_icon.py` can trace one from the
cutout's alpha mask:

```bash
python3 tools/make_icon.py --all --dry-run     # what the licence gate allows
python3 tools/make_icon.py radarsat-2          # write one icon + its ATTRIBUTIONS row
python3 tools/make_icon.py smap --fill-holes --force   # see below
```

**`--fill-holes`, for see-through structures.** Some spacecraft are transparent where
they should read as solid: a mesh reflector, an open truss, a gapped array. The
publisher's alpha is right — you really can see space through a mesh dish — but traced
straight it leaves a hollow wireframe that falls apart at 16px. `--fill-holes` fills any
*fully enclosed* transparent region before tracing, so the dish becomes a disc while
anything open to the edge of the frame stays open. SMAP's reflector is the case it was
written for. Use it when a silhouette looks like a wireframe rather than a shape; do not
use it by default, because the gap between a bus and its solar wing is enclosed in some
poses too, and filling that fuses them into a blob. A picks row may also carry
`"fill_holes": true`, applied with `--picks`.

**The licence gate is the whole point of this tool.** An icon is a new published
derivative, so the source needs an explicit grant to adapt: public domain, an
adaptation-permitting CC licence, or a government open licence that says so in its own
terms (UK OGL v3, OGL Canada, KOGL Type 1). Every ESA Standard Licence photo is refused
— ESA ruled background removal impermissible in writing — as is media-terms imagery, any
NC/ND variant, higher KOGL types, and any licence string the tooling does not
recognise. There is no override flag. Refused folders keep their photo
and have no icon, which is a supported state, not a gap to fill. Existing hand-drawn
icons are never overwritten: they are original artwork and outrank anything traced.

## House artwork lane (generated)

**This lane exists for folders that can never have a photograph.** After the
open-licence batches and the agency replies, roughly 60 operational missions
belong to owners who refuse derivatives or will not answer (Roskosmos, CNSA,
CMA, NSOAS) plus 15 to GHGSat. An original depiction is the only legal route to
a visual for those. It is also the only route to an *icon* for the eleven ESA
folders, because ESA refused background removal in writing and
`make_icon.py` therefore refuses to trace their photos — see the ESA rules above.

### The legal frame, in full

Golden rule 6 is the whole basis of this lane, so read it as a rule about
process, not about output:

- **A photograph may be looked at. It may never be traced.** Drawing the
  spacecraft in our house style, using photographs only as reference for what it
  looks like, is our own copyright. A 1:1 trace of one specific render copies
  that image's composition and is a derivative of it.
- **The tooling makes tracing impossible by construction, not by discipline.**
  `tools/house_art/kit.py` takes numbers and returns polygons. It has no image
  input and no code path that could acquire one. What a person looks at while
  writing `description.json` never reaches the drawing.
- **Reference images are never stored in this repository.** They are fetched to
  `tools/out/` (gitignored) so a person can look at them while writing the
  description and while reviewing the result. Looking is not reuse; hosting is.
  What the repository keeps is the URL list, in the entry's `references` field.
  `check_index.py` enforces that those are URLs.
- **This is the one place the strict sourcing rule does not apply.** Golden rule
  2 bans general web search *for images we intend to host*. Nothing here is
  hosted, so any source may be consulted — agency pages, eoPortal, Gunter's
  Space Page, Wikipedia. `commons_gather.py` remains the strict tool for the
  photo lane; `house_art/refs.py` is the permissive one for this lane.
- **The icon comes from our own SVG.** `<folder>-icon.svg` is the union
  silhouette of the colour drawing's structural shapes, re-emitted in
  `fill:currentColor`. It is never derived from a photograph. The photo-derived
  icon lane is `make_icon.py` and keeps its own, stricter licence gate.

### When to use it

Use it when: the owner's licence refuses derivatives or no licence is
obtainable; or the folder has an ESA Standard Licence photo and therefore cannot
have a traced icon.

Do **not** use it to replace any of the 72 existing hand-drawn SVGs. Those are
original artwork and outrank anything generated. Do not use it where a licensed
photograph is obtainable — golden rule 6's own reasoning is that a licensed
photo is a better answer than a drawing.

### Evidence grades

Every description carries a grade, and the review page shows it:

| Grade | Meaning |
|---|---|
| A | agency render plus photographs |
| B | one clear image of the spacecraft |
| C | thin: a single diagram, or only imagery of a sibling vehicle |

Grade C is legitimate — for several of these owners it is all that exists — but
it is where a wrong drawing is most likely to pass unnoticed, so batch the C
rows small and give them more review attention. A reference that turns out to
show a different vehicle, or the mission's data rather than its hardware, stays
in the list marked `used_for_geometry: false` and is shown greyed out on the
review page. It is not quietly dropped: what was rejected is part of the record.

### The workflow

```bash
# 1. Generate candidates into the gitignored working directory. Each folder gets
#    description.json, <folder>.svg, <folder>-icon.svg, renders, checks.json and
#    originality.json under tools/out/house_art/<folder>/.
#    The build runs two gates and fails loudly:
#      - description <-> drawing: every solid is tagged with the element it
#        depicts, and the two sets must match. A part in the artwork that is in
#        no description is refused.
#      - projected geometry: assertions on the 2D result after occlusion. An
#        element that is correct in 3D and invisible on screen is refused, as is
#        a masted antenna that reads as detached.

# 2. Build the review page and review it.
python3 tools/make_art_checker.py
open tools/out/art_checker.html          # Approve / Regenerate / Reject, Export

# 3. Apply the approved picks.
python3 tools/apply_art.py ~/Downloads/art-picks.json
cd tools && npm install && node render_pngs.mjs
python3 tools/check_index.py
git diff                                  # then branch, commit, PR
```

`apply_art.py` writes `<folder>.svg`, `<folder>-icon.svg`, the index entry
(`artStatus: house-generated`, `references`, artwork paths) and the
ATTRIBUTIONS rows (repo maintainers, CC BY 4.0, with the method recorded). It
refuses a folder whose description has no reference URLs, and goes through the
shared folder-name guard in `index_utils` before anything touches the filesystem.

### Originality scoring, and why the raw number is not the answer

Each drawing is scored by edge overlap against its own references — and against
a **control**: the same drawing scored the same way against every *other*
mission's references. Measured over a 20-target batch, drawings scored a mean
0.20 against their own references and 0.19 against unrelated ones: the same
distribution. Any two spacecraft share body-plus-wings edge structure, so a raw
score means very little.

**Read the margin over the control's 95th percentile, not the raw score.** A
drawing that scores no higher against its own references than against strangers'
is not copying anything. When the margin does run high, open the edge overlay:
it shows whether the resemblance is "same spacecraft" or "same picture". A body
of revolution seen near side-on will always score high against another near
side-on view; the fix is to change our camera, not to argue with the number.

### Budget two review rounds

Both pilots produced real corrections in round one that no automated check would
have found: an antenna that read as a drinking straw, a mast that read as a
chimney, a dish that looked detached, umbrella spokes that read inconsistently
around the canopy. These are drawing-*reading* problems and they need a person.
Plan for two rounds per batch rather than hoping for one. Roughly a third of a
first batch comes back; under a tenth of the second.

### Open: the 16 px icon question — George decides

Some spacecraft do not survive 16 px. Widely spaced arrays on outrigger booms
break into three disconnected blobs; very long thin wings become a hairline.
This is a property of the vehicle, not a defect in the drawing, and no amount of
redrawing fixes it without making the artwork wrong.

`house_art.checks.icon_legibility()` flags these, and the review page offers
**icon: keep / icon: drop** on the affected rows. **The policy is not decided.**
The options are:

1. ship the honest icon and accept that it is mush at 16 px;
2. drop the icon for those folders — a supported state, lists simply omit it;
3. draw a separate 16 px variant with the arrays pulled in — accurate at a
   glance, wrong in detail, and a second asset to keep in step.

Until George decides, `apply_art.py` honours the per-row choice from the review
page and neither option is the default. Do not settle this by convention in a
batch PR.


## Who decides what

- Image is right/wrong, licence reads OK → you decide, PR review catches mistakes.
- Tier D / permission emails / anything legal-ish → George.
- Mission-ID ambiguity → George (Task B).
- Tooling broken or a source that should be automated → flag it in an issue; Claude Code sessions maintain `tools/`.
