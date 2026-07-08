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
6. **SVGs must be original depictions, not traces.** Drawing the satellite in our house style (using photos only as reference for what it looks like) is our own copyright. A 1:1 trace of one specific render copies that image's composition and is a derivative — don't do it, and flag any existing SVG that looks like one.
7. **Logos are never redrawn** — official files only (see Task C).
8. **All work on branches, PR per batch, never commit to `main`.** Keep commit messages plain (no generated-by/co-author trailers).

## Task A — satellite photos (the main job)

Goal: every mission folder gets a properly licensed photo/render of the spacecraft, recorded in `index.json` with `imageStatus: licensed`. Where none exists, `imageStatus: svg-fallback` — the SVG is the visual, and that's fine.

**One folder per visual design, not per mission.** The portal's API maps mission variants onto a folder (Sentinel-1A and 1B both use `sentinel-1`; 1C/1D use `sentinel-1c` because they look different). So a photo of *any* visually-identical unit serves the whole series — note which unit it shows in the ATTRIBUTIONS title if known. Only make a new folder when a block/generation genuinely looks different.

The workflow (from the repo root):

```bash
# 1. Gather candidates for every entry still pending (or name specific folders)
python3 tools/commons_gather.py

# 2. Build the review gallery and open it in a browser
python3 tools/make_gallery.py
open tools/out/gallery.html
```

3. **Pick.** This is the judgement step a script can't do: most search hits are the satellite's *data* (pretty pictures of Earth), not the satellite. Pick the best image *of the spacecraft* — official renders and pre-launch cleanroom photos both count (golden rule 3: agency/manufacturer imagery only). Between licence-equal candidates, prefer one where the spacecraft is fully in frame against an uncluttered background — after your batch merges, the maintainers derive transparent cutouts from these photos for the portal, and clean subjects cut best. Leave "none of these" selected if nothing shows the spacecraft. Click **Export picks** (downloads `picks.json`).

```bash
# 4. Apply: downloads each pick and writes all the paperwork
python3 tools/apply_picks.py ~/Downloads/picks.json

# 5. Review what changed, then branch/commit/PR
git diff
git checkout -b feat/photos-batch-01
git add -A && git commit -m "Photos batch 1: <folders>"
git push -u origin feat/photos-batch-01   # then open a PR
```

**In the PR description, list each mission and its licence** (batch 1 skipped this — required from batch 2 on). The reviewer checks: is it actually the right satellite, is the licence real (click through to the source page), is the credit sensible.

Batch size: ~20–25 missions per PR (batch 1 landed 22 and reviewed comfortably).

For the ~14 missions Commons can't cover, `image-sourcing-manual-worklist.csv` lists each owner's image library and the licence you're looking for — same paperwork, found by hand. Tier D rows: rule 5 applies, and the ladder below is how permission actually gets obtained.

**After your batch merges (not your job):** the maintainers run `tools/process_photos.py` over the new photos to derive transparent cutouts (`-photo-cut-1024px/-512px.png`) with their own paperwork. Your only lever on that step is picking cuttable images. Anything the cutter can't handle goes on the re-source list — current priorities are in issue #113 (plus ace and sentinel-3 from batch 1, which need proper agency imagery; for Sentinels, ESA's multimedia library publishes renders under CC BY-SA 3.0 IGO, which qualifies).

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

Twelve `index.json` entries have an empty `missionID` because the mapping needs a human call (e.g. the `sentinel-1` folder vs per-satellite A/B/C DB rows; the `ace` folder, whose image is probably the 1997 Advanced Composition Explorer, not missionID 648). Issue #99 has the full list and notes. Resolve each with George — the answer is sometimes "this folder maps to no mission and should be moved to `other-spacecraft/`".

## Task C — agency/provider logos (issue #101)

New asset class under `agencies/<acronym-lowercase>/`, same schema and paperwork as satellites. Differences:

- Logos are **trademarks**: we use them only to identify the agency next to its own missions. The licence bar is different — record `imageStatus: trademark-editorial-use` plus the brand-terms URL when a logo isn't openly licensed but its brand page permits editorial use.
- **Official files only, never redrawn.** SVG preferred.
- Sourcing ladder: (1) Wikimedia Commons — US-gov agency logos are public domain, simple text logos are often `PD-textlogo`; note that logos on *English Wikipedia* (rather than Commons) are usually fair-use and NOT usable. (2) The agency/company's own brand or press page. (3) No logo → the portal shows a text chip, which is fine.
- Priority: the ~35 CEOS member agencies first (ceos.org's member page is the reference for the *current* logo), then commercial providers (ICEYE, Umbra, iQPS, Planet, Capella, SatVu, Airbus…).
- `tools/commons_gather.py --terms "ESA logo" --key esa-logo` reuses the *gather and gallery* steps for logo searches. `apply_picks.py` only handles satellite folders — for logos, download the picked file and do the paperwork (folder, index entry, `ATTRIBUTIONS.csv` row) by hand until a logo-aware apply tool exists.

## Adding a brand-new satellite folder

1. Create `satellites/<name>/` — lowercase, matching the portal's naming (ask if unsure).
2. Add `<name>.svg` (colour) and `<name>-icon.svg` (mono) — your original artwork.
3. `cd tools && npm install && node render_pngs.mjs` regenerates the PNGs.
4. Add the `index.json` entry (copy an existing one; missionID from George/the API).
5. `ATTRIBUTIONS.csv` rows for the new files (repo maintainers, CC BY 4.0).

## Who decides what

- Image is right/wrong, licence reads OK → you decide, PR review catches mistakes.
- Tier D / permission emails / anything legal-ish → George.
- Mission-ID ambiguity → George (Task B).
- Tooling broken or a source that should be automated → flag it in an issue; Claude Code sessions maintain `tools/`.
