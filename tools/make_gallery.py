#!/usr/bin/env python3
"""Render tools/out/candidates.json as a clickable review gallery.

Open tools/out/gallery.html in a browser, pick at most one image per
mission (or "none of these"), then click "Export picks" to download
picks.json. Apply it with tools/apply_picks.py.

The gallery is a disposable artifact — tools/out/ is gitignored.
"""

import html
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tools" / "out"

candidates = json.load(open(OUT / "candidates.json"))

cards = []
for key, block in sorted(candidates.items()):
    options = []
    for i, c in enumerate(block["candidates"]):
        options.append(f"""
        <label class="card">
          <input type="radio" name="{html.escape(key)}" value="{i}">
          <img src="{html.escape(c['thumb'])}" loading="lazy">
          <div class="meta">
            <div class="t">{html.escape(c['title'])}</div>
            <div>{html.escape(c['licence'])} — {html.escape(c['credit'][:80])}</div>
            <a href="{html.escape(c['page'])}" target="_blank">source page</a>
          </div>
        </label>""")
    cards.append(f"""
    <section data-key="{html.escape(key)}">
      <h2>{html.escape(key)} <small>{html.escape(block.get('missionName', ''))}</small></h2>
      <label class="card none"><input type="radio" name="{html.escape(key)}" value="none" checked> none of these</label>
      {''.join(options)}
    </section>""")

# "</" -> "<\/" so external-API strings (titles/credits) cannot close the
# script element; the escape is a no-op to the JSON parser.
data_json = json.dumps(candidates).replace("</", "<\\/")

page = f"""<!doctype html>
<meta charset="utf-8">
<title>satellite-visuals candidate review</title>
<style>
 body {{ font: 14px/1.4 system-ui; margin: 2rem; }}
 section {{ border-top: 1px solid #ccc; padding: 1rem 0; }}
 .card {{ display: inline-block; width: 240px; vertical-align: top; margin: 0 8px 8px 0;
          border: 2px solid #ddd; border-radius: 6px; padding: 6px; cursor: pointer; }}
 .card:has(input:checked) {{ border-color: #0a7; background: #f0fbf7; }}
 .card img {{ max-width: 100%; max-height: 160px; display: block; margin: auto; }}
 .card .t {{ font-weight: 600; overflow-wrap: anywhere; }}
 .none {{ width: auto; }}
 #export {{ position: fixed; top: 1rem; right: 1rem; padding: .6rem 1rem; }}
</style>
<button id="export">Export picks</button>
{''.join(cards)}
<script>
const DATA = {data_json};
document.getElementById('export').onclick = () => {{
  const picks = {{}};
  for (const section of document.querySelectorAll('section')) {{
    const key = section.dataset.key;
    const sel = section.querySelector('input:checked');
    if (sel && sel.value !== 'none') picks[key] = DATA[key].candidates[Number(sel.value)];
  }}
  const blob = new Blob([JSON.stringify(picks, null, 2)], {{type: 'application/json'}});
  const a = Object.assign(document.createElement('a'), {{
    href: URL.createObjectURL(blob), download: 'picks.json'
  }});
  a.click();
}};
</script>
"""

path = OUT / "gallery.html"
path.write_text(page)
print(f"Wrote {path.relative_to(REPO)} — open it in a browser, pick, Export picks.")
