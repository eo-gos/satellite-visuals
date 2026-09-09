#!/usr/bin/env python3
"""Render a batch review page: one row per folder, candidates side by side.

This is the maintainer-facing counterpart to make_gallery.py. make_gallery.py
reviews *search hits* (many small thumbnails, one licence class); this renders a
*curated shortlist* — a handful of candidates per folder, each already checked
against its source page, with the exact paperwork that would be written shown
next to the image so the reviewer approves the record, not just the picture.

    python3 tools/make_checker.py                      # tools/out/checker.html
    python3 tools/make_checker.py --out ~/Desktop/x.html

Input is tools/out/checker_data.json (gitignored, built per batch). Shape:

    {"generated": "...", "noticeUrl": "...", "rows": [
       {"folder": "sentinel-3", "lane": "esa"|"esa-eum"|"pd"|"cc",
        "missionName": ..., "missionID": ..., "currentStatus": ...,
        "currentLicence": ..., "currentCredit": ..., "headline": ...,
        "noneReason": "why nothing was found (empty when there are candidates)",
        "extra": "row-level warning shown in a callout",
        "alts": [{"title","page","url","credit","artist","licence_text",
                  "dim","alpha","ext","img" (data URI),
                  "verdict": "recommend"|"alternate"|"reject", "note",
                  "rights_holder"?, "credit_line"?, "notes"?}]}]}

``rights_holder`` / ``credit_line`` override what the export writes as the
rights holder and the credit line, and ``notes`` becomes the ATTRIBUTIONS notes
column. Set them whenever the source's own metadata is not a usable credit —
Wikimedia Commons, for instance, puts the Flickr photo title in its "Credit"
field, which is a caption, not a rights holder.

Output is one self-contained HTML file — images are inlined as data URIs, so it
works opened from disk with no server and no sibling files. The Export picks
button downloads picks.json for tools/apply_clean.py.

Lanes decide the paperwork the page promises:
  esa / esa-eum  ESA Standard Licence (or CC BY-SA 3.0 IGO where the ESA page
                 offers it) -> clean render, resize only, licenceNoticeUrl set.
                 Never cut: ESA refused background removal in writing.
  pd / cc        ordinary sourced photo -> raw file, cuttable later.
"""

import argparse
import html
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tools" / "out"

LANE_LABEL = {
    "esa": "ESA lane",
    "esa-eum": "ESA lane (joint ESA/EUMETSAT mission)",
    "pd": "US public domain",
    "cc": "CC BY-SA pending",
}

CSS = """
:root { --ink:#16181d; --muted:#5b6270; --line:#d8dce3; --bg:#f6f7f9;
        --ok:#0a7f52; --warn:#a35b00; --bad:#a32020; --esa:#1b4fa8; }
* { box-sizing:border-box; }
body { font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
       margin:0; color:var(--ink); background:var(--bg); }
header { position:sticky; top:0; z-index:5; background:#fff; border-bottom:1px solid var(--line);
         padding:14px 24px; display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap; }
header h1 { font-size:18px; margin:0 0 4px; }
header .counts { color:var(--muted); font-size:13px; }
header .counts b { color:var(--ink); }
#export { margin-left:auto; padding:10px 18px; font-size:15px; font-weight:600;
          background:var(--ink); color:#fff; border:0; border-radius:6px; cursor:pointer; }
#export:hover { background:#000; }
main { padding:24px; max-width:1500px; }
.summary { background:#fff; border:1px solid var(--line); border-radius:8px;
           padding:16px 20px; margin-bottom:24px; }
.summary h2 { font-size:14px; text-transform:uppercase; letter-spacing:.04em;
              color:var(--muted); margin:0 0 10px; }
.summary li { margin-bottom:6px; }
.summary code { background:var(--bg); padding:1px 5px; border-radius:3px; }
section { background:#fff; border:1px solid var(--line); border-radius:8px;
          margin-bottom:22px; overflow:hidden; }
section.done { border-color:var(--ok); box-shadow:0 0 0 1px var(--ok); }
.head { padding:14px 20px; border-bottom:1px solid var(--line); display:flex;
        gap:14px; align-items:baseline; flex-wrap:wrap; }
.head h2 { font-size:17px; margin:0; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.head .mission { color:var(--muted); }
.badge { font-size:11px; text-transform:uppercase; letter-spacing:.05em; font-weight:700;
         padding:3px 8px; border-radius:99px; border:1px solid; }
.badge.esa { color:var(--esa); border-color:var(--esa); }
.badge.pd  { color:var(--ok); border-color:var(--ok); }
.badge.cc  { color:var(--warn); border-color:var(--warn); }
.headline { margin-left:auto; font-weight:600; }
.esa-marker { margin:12px 20px 0; padding:9px 12px; border-left:3px solid var(--esa);
              background:#eef3fc; font-size:13px; }
.callout { margin:12px 20px 0; padding:9px 12px; border-left:3px solid var(--warn);
           background:#fff6e9; font-size:13px; }
.nonefound { margin:12px 20px 16px; padding:9px 12px; border-left:3px solid var(--muted);
             background:var(--bg); font-size:13px; color:var(--muted); }
.cards { display:flex; gap:16px; padding:16px 20px; overflow-x:auto; align-items:flex-start; }
.card { flex:0 0 460px; border:2px solid var(--line); border-radius:6px; padding:12px;
        background:#fff; }
.card.sel { border-color:var(--ok); background:#f2fbf7; }
.card.rejectable { opacity:.72; }
.card img { width:100%; background:
    repeating-conic-gradient(#e9ecef 0 25%, #fff 0 50%) 50%/18px 18px; border-radius:4px;
    display:block; }
.card h3 { font-size:14px; margin:10px 0 6px; }
.v { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; }
.v.recommend { color:var(--ok); } .v.alternate { color:var(--warn); } .v.reject { color:var(--bad); }
.note { font-size:13px; color:var(--muted); margin:6px 0 10px; }
table.paper { width:100%; border-collapse:collapse; font-size:12.5px; }
table.paper th { text-align:left; color:var(--muted); font-weight:600; width:132px;
                 padding:3px 8px 3px 0; vertical-align:top; }
table.paper td { padding:3px 0; vertical-align:top; word-break:break-word; }
.controls { padding:12px 20px 18px; display:flex; gap:18px; align-items:center;
            flex-wrap:wrap; border-top:1px solid var(--line); background:#fbfcfd; }
.controls label { display:flex; gap:6px; align-items:center; font-size:14px; }
.controls select { font:inherit; padding:4px 6px; }
.state { font-size:13px; color:var(--muted); margin-left:auto; }
a { color:#1155cc; }
"""


def card_html(row, i, alt):
    lane_esa = row["lane"].startswith("esa")
    status = "licensed"
    licence_shown = alt.get("record_licence") or (
        "ESA Standard Licence" if lane_esa else alt.get("licence_text", ""))
    rights = alt.get("credit") or alt.get("artist") or ""
    paper = [
        ("Source page", f'<a href="{html.escape(alt["page"])}" target="_blank" rel="noreferrer">'
                        f'{html.escape(alt["page"])}</a>'),
        ("File", f'<a href="{html.escape(alt["url"])}" target="_blank" rel="noreferrer">'
                 f'{html.escape(alt["url"].rsplit("/", 1)[-1])}</a> · {html.escape(alt["dim"])}'
                 + (" · <b>alpha channel</b>" if alt.get("alpha") else "")),
        ("Licence on page", html.escape(alt.get("licence_text", ""))),
        ("Licence recorded", html.escape(licence_shown)),
        ("Rights holder", html.escape(rights)),
        ("Credit line", f"<b>{html.escape(alt.get('credit') or alt.get('artist') or '')}</b>"),
        ("imageStatus", html.escape(status)),
    ]
    if lane_esa:
        paper.append(("licenceNoticeUrl", "set when the licence recorded is the ESA "
                                          "Standard Licence"))
    rows_html = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in paper)
    return f"""
      <div class="card {'rejectable' if alt['verdict'] == 'reject' else ''}"
           data-folder="{html.escape(row['folder'])}" data-idx="{i}">
        <img src="{alt['img']}" alt="{html.escape(alt['title'])}">
        <h3>{html.escape(alt['title'])} <span class="v {alt['verdict']}">
            {'recommended' if alt['verdict'] == 'recommend' else alt['verdict']}</span></h3>
        <p class="note">{html.escape(alt['note'])}</p>
        <table class="paper">{rows_html}</table>
      </div>"""


def section_html(row):
    lane = row["lane"]
    badge = "esa" if lane.startswith("esa") else ("pd" if lane == "pd" else "cc")
    cards = "".join(card_html(row, i, a) for i, a in enumerate(row["alts"]))
    pieces = []
    takeable = any(a["verdict"] != "reject" for a in row["alts"])
    if lane.startswith("esa") and takeable:
        pieces.append('<div class="esa-marker"><b>ESA clean render, resize only, notice URL '
                      'will be set.</b> No background removal, no cropping, no compositing — '
                      'the archival file is stored as published and the 1024px/512px display '
                      'PNGs are scaled from it (alpha preserved where present).</div>')
    if row.get("extra"):
        pieces.append(f'<div class="callout">{html.escape(row["extra"])}</div>')
    if row.get("noneReason"):
        pieces.append(f'<div class="nonefound"><b>No candidate found.</b> '
                      f'{html.escape(row["noneReason"])}</div>')
    if cards:
        pieces.append(f'<div class="cards">{cards}</div>')
        opts = "".join(
            f'<option value="{i}">{"Approve — " if a["verdict"] == "recommend" else f"Alternate {i} — "}'
            f'{html.escape(a["title"][:60])}</option>'
            for i, a in enumerate(row["alts"]) if a["verdict"] != "reject")
        lic = ""
        if "CC BY-SA 3.0 IGO" in " ".join(a.get("licence_text", "") for a in row["alts"]):
            lic = ('<label>Licence to record '
                   '<select class="lic"><option>ESA Standard Licence</option>'
                   '<option>CC BY-SA 3.0 IGO</option></select></label>')
        pieces.append(f"""
      <div class="controls">
        <label><input type="radio" name="{html.escape(row['folder'])}" value="none" checked> Reject / skip</label>
        <label><input type="radio" name="{html.escape(row['folder'])}" value="pick">
          <select class="pick">{opts}</select></label>
        {lic}
        <span class="state">no pick</span>
      </div>""")
    return f"""
    <section id="{html.escape(row['folder'])}" data-folder="{html.escape(row['folder'])}"
             data-lane="{html.escape(lane)}">
      <div class="head">
        <h2>{html.escape(row['folder'])}</h2>
        <span class="mission">{html.escape(row['missionName'])} · missionID
          {html.escape(str(row['missionID']))} · now <code>{html.escape(row['currentStatus'])}</code></span>
        <span class="badge {badge}">{html.escape(LANE_LABEL[lane])}</span>
        <span class="headline">{html.escape(row['headline'])}</span>
      </div>
      {''.join(pieces)}
    </section>"""


def build(data):
    rows = data["rows"]
    with_cand = [r for r in rows if any(a["verdict"] != "reject" for a in r["alts"])]
    without = [r for r in rows if not any(a["verdict"] != "reject" for a in r["alts"])]
    esa = [r for r in with_cand if r["lane"].startswith("esa")]
    other = [r for r in with_cand if not r["lane"].startswith("esa")]
    none_list = "".join(
        f"<li><code>{html.escape(r['folder'])}</code> — "
        f"{html.escape(r.get('noneReason') or (r['alts'][0]['note'] if r['alts'] else ''))}</li>"
        for r in without)
    sections = "".join(section_html(r) for r in rows)
    payload = json.dumps({r["folder"]: r for r in rows}).replace("</", "<\\/")
    return f"""<!doctype html>
<meta charset="utf-8">
<title>satellite-visuals — Batch A review</title>
<style>{CSS}</style>
<header>
  <div>
    <h1>satellite-visuals — Batch A review</h1>
    <div class="counts">
      branch <b>{html.escape(data.get('branch', ''))}</b> ·
      <b>{len(rows)}</b> folders reviewed ·
      <b>{len(with_cand)}</b> with a candidate
      (<b>{len(esa)}</b> ESA clean renders, <b>{len(other)}</b> photo picks) ·
      <b>{len(without)}</b> with nothing usable
    </div>
  </div>
  <button id="export">Export picks &darr; picks.json</button>
</header>
<main>
  <div class="summary">
    <h2>Nothing found for these</h2>
    <ul>{none_list}</ul>
    <h2 style="margin-top:14px">How to use this page</h2>
    <ul>
      <li>Each row defaults to <b>Reject / skip</b> — only the rows you actively set are exported.</li>
      <li>Pick the candidate from the dropdown, then export. ESA rows write a clean render
          (resize only); public-domain rows write a raw photo that can be cut later.</li>
      <li>Export downloads <code>picks.json</code>. Apply it with
          <code>python3 tools/apply_clean.py ~/Downloads/picks.json</code>, then run
          <code>python3 tools/check_index.py</code> before committing.</li>
    </ul>
  </div>
  {sections}
</main>
<script>
const DATA = {payload};
const NOTICE = {json.dumps(data['noticeUrl'])};

function refresh(section) {{
  const folder = section.dataset.folder;
  const sel = section.querySelector('input[type=radio]:checked');
  const pick = section.querySelector('.pick');
  const state = section.querySelector('.state');
  section.querySelectorAll('.card').forEach(c => c.classList.remove('sel'));
  if (!sel || sel.value === 'none') {{
    section.classList.remove('done');
    if (state) state.textContent = 'no pick';
    return;
  }}
  const i = Number(pick.value);
  section.classList.add('done');
  const card = section.querySelector(`.card[data-idx="${{i}}"]`);
  if (card) card.classList.add('sel');
  if (state) state.textContent = 'will be written for ' + folder;
}}

document.querySelectorAll('section').forEach(s => {{
  s.addEventListener('change', e => {{
    if (e.target.classList.contains('pick')) {{
      const radio = s.querySelector('input[value="pick"]');
      if (radio) radio.checked = true;
    }}
    refresh(s);
  }});
  refresh(s);
}});

document.getElementById('export').onclick = () => {{
  const picks = {{schema: 'satellite-visuals/picks/2',
                 generated: new Date().toISOString(),
                 esa_clean: {{}}, photos: {{}}}};
  document.querySelectorAll('section').forEach(s => {{
    const folder = s.dataset.folder;
    const sel = s.querySelector('input[type=radio]:checked');
    if (!sel || sel.value === 'none') return;
    const alt = DATA[folder].alts[Number(s.querySelector('.pick').value)];
    const licSel = s.querySelector('.lic');
    const esa = s.dataset.lane.startsWith('esa');
    const licence = esa ? (licSel ? licSel.value : 'ESA Standard Licence')
                        : (alt.licence_text || '');
    // Commons download URLs carry a utm query string, and its last dot-segment
    // is not a file extension — take the extension from the path, and hand the
    // apply step the URL without the tracking query.
    const url = alt.url.split('?')[0].split('#')[0];
    const ext = (alt.ext && !/[?&=]/.test(alt.ext))
                ? alt.ext.toLowerCase()
                : (url.split('/').pop().split('.').pop() || '').toLowerCase();
    // rights_holder is the curated value; Commons' "Credit" field is often just
    // the Flickr photo title, so it is the last resort, never the first.
    const rights = alt.rights_holder || alt.artist || alt.credit || '';
    const rec = {{title: alt.title, page: alt.page, url: url, ext: ext,
                 credit: alt.credit_line || rights, rights_holder: rights,
                 licence: licence, status: 'licensed'}};
    if (alt.notes) rec.notes = alt.notes;
    if (esa) {{
      if (licence === 'ESA Standard Licence') rec.licence_notice_url = NOTICE;
      picks.esa_clean[folder] = rec;
    }} else {{
      rec.artist = alt.artist || rights;
      picks.photos[folder] = rec;
    }}
  }});
  const blob = new Blob([JSON.stringify(picks, null, 2)], {{type: 'application/json'}});
  const a = Object.assign(document.createElement('a'),
    {{href: URL.createObjectURL(blob), download: 'picks.json'}});
  a.click();
}};
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(OUT / "checker_data.json"))
    ap.add_argument("--out", action="append", default=None,
                    help="output path (repeatable; default tools/out/checker.html)")
    args = ap.parse_args()
    data = json.load(open(args.data))
    page = build(data)
    for target in (args.out or [str(OUT / "checker.html")]):
        p = Path(target).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(page)
        print(f"Wrote {p}  ({len(page) // 1024} KB)")


if __name__ == "__main__":
    main()
