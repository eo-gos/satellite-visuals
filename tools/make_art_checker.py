#!/usr/bin/env python3
"""Build the house-artwork review page from a working directory of candidates.

The review page is the human check the lane is built around: reference
thumbnails beside our drawing, the description the drawing was written from, the
evidence grade, the originality margin, and Approve / Regenerate / Reject per
row with a JSON export. It is a single self-contained file, so it can be opened
from disk and mailed around.

    python3 tools/make_art_checker.py                  # every candidate
    python3 tools/make_art_checker.py biomass fy-3e    # named folders
    open tools/out/art_checker.html                    # review, Export

Then feed the exported picks to `tools/apply_art.py`.

Working-directory layout (all of it gitignored, none of it committed):

    tools/out/house_art/<folder>/
        description.json          the drawing's input, and the reference URLs
        <folder>.svg              colour artwork
        <folder>-icon.svg         mono icon, derived from the colour SVG
        <folder>-render.png       raster of the colour SVG, for the page
        <folder>-icon-render.png  raster of the icon, for the 16 px check
        originality.json          margin against the control distribution
        checks.json               build-check results
        references.json           local paths of the fetched references
"""

import argparse
import base64
import html
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from house_art import checks as art_checks  # noqa: E402
from house_art import schema  # noqa: E402
from house_art.refs import OUT, local_path  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "tools" / "out" / "art_checker.html"

GRADE_TEXT = {"A": "agency render plus photographs",
              "B": "one clear image of the spacecraft",
              "C": "thin: a single diagram, or only sibling-vehicle imagery"}


def esc(value):
    return html.escape(str(value), quote=True)


def data_uri(path, width=320, quality=74):
    from PIL import Image
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    im = im.convert("RGB")
    im.thumbnail((width, width), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def inline_svg(path, cls):
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r"<\?xml[^>]*\?>\s*", "", text)
    text = re.sub(r'\swidth="[^"]*"', "", text, count=1)
    text = re.sub(r'\sheight="[^"]*"', "", text, count=1)
    return text.replace("<svg ", f'<svg class="{cls}" preserveAspectRatio="xMidYMid meet" ', 1)


def summarise(d):
    bits = []
    bus = d.get("bus") or {}
    if bus.get("dims_m"):
        bits.append(f"Bus: {bus.get('form', 'box')}, "
                    f"{' x '.join(str(v) for v in bus['dims_m'])} m, {bus.get('finish', '')}")
    elif bus.get("form"):
        bits.append(f"Bus: {bus['form']}")
    solar = d.get("solar") or {}
    if solar.get("wings"):
        bits.append(f"{solar['wings']} wing{'s' if solar['wings'] != 1 else ''} x "
                    f"{solar['panels_per_wing']} panels"
                    + (f" ({solar['layout']})" if solar.get("layout") else "")
                    + f", {solar.get('mount', '')}")
    else:
        bits.append(solar.get("note", "no deployable array"))
    for key in ("instruments", "antennas", "booms"):
        for item in d.get(key) or []:
            bits.append(f"{item['name']}: {item.get('form', '')}"
                        + (f", {item['diameter_m']} m" if item.get("diameter_m") else "")
                        + (f", {item['length_m']} m" if item.get("length_m") else ""))
    return bits


def row_html(folder, d, orig, chk, icon16, refs_local):
    thumbs = []
    for r in d.get("references", []):
        page = r.get("source_page") or ""
        if not r.get("downloaded"):
            thumbs.append(
                f'<div class="ref textref"><a href="{esc(page)}" target="_blank" rel="noopener">'
                f'<span>text reference<br>no image stored</span></a>'
                f'<div class="refmeta">{esc(r.get("credit", ""))}</div></div>')
            continue
        path = refs_local.get(r.get("n"))
        if not path or not Path(path).exists():
            continue
        cls = "used" if r.get("used_for_geometry") else "unused"
        tail = "" if r.get("used_for_geometry") else " &middot; <b>not this spacecraft, unused</b>"
        thumbs.append(
            f'<div class="ref {cls}"><a href="{esc(page)}" target="_blank" rel="noopener">'
            f'<img src="{data_uri(path)}" alt="reference {r.get("n")}"></a>'
            f'<div class="refmeta">ref {r.get("n")} &middot; {esc(r.get("credit", ""))}{tail}</div></div>')

    base = OUT / folder
    icon_ctrl = ""
    if icon16 and not icon16["legible"]:
        icon_ctrl = (f'<span class="iconq">Icon breaks into {icon16["components"]} '
                     f'pieces at 16&nbsp;px.</span>'
                     '<button class="btn keep" data-act="keep">Icon: keep</button>'
                     '<button class="btn drop" data-act="drop">Icon: drop</button>')

    share = d.get("shares_bus_with")
    share_html = (f'<p class="share"><b>Shared bus:</b> same platform as '
                  f'<code>{esc(share["folder"])}</code> &mdash; {esc(share.get("note", ""))}'
                  f'</p>' if share else "")

    checks_html = "".join(
        f'<li>{esc(c["check"])}: <b class="{"ok" if c["ok"] else "bad"}">'
        f'{"pass" if c["ok"] else "FAIL"}</b>'
        + (f' &mdash; {esc("; ".join(c["problems"]))}' if c.get("problems") else "")
        + "</li>" for c in (chk.get("checks") or []))

    ovl = base / "originality-overlay.png"
    overlay = f'<img class="overlay" src="{data_uri(ovl, 300, 80)}">' if ovl.exists() else ""
    verdict = {"PASS": "ok", "REVIEW": "warn", "FAIL": "bad"}[orig["overall"]]
    margin = orig.get("margin_over_control_p95")
    grade = d.get("evidence", "C")

    return f"""
<section class="row" data-folder="{esc(folder)}">
  <header class="rowhead">
    <div><h2>{esc(d.get("mission", folder))}</h2>
      <div class="sub"><code>{esc(folder)}</code>
        {(" &middot; " + esc(d["owner"])) if d.get("owner") else ""}
        {(" &middot; CEOS mission " + esc(d["mission_id"])) if d.get("mission_id") else ""}</div></div>
    <div class="grade g{esc(grade)}" title="{esc(GRADE_TEXT.get(grade, ''))}">evidence {esc(grade)}</div>
    <div class="state">undecided</div>
  </header>
  <div class="grid">
    <div class="col">
      <h3>References ({sum(1 for r in d.get("references", []) if r.get("downloaded"))} images,
        {sum(1 for r in d.get("references", []) if r.get("used_for_geometry"))} used)</h3>
      <div class="refstrip">{''.join(thumbs)}</div>
      <p class="caveat"><b>Evidence {esc(grade)}:</b> {esc(d.get("evidence_note", ""))}</p>
      {share_html}
    </div>
    <div class="col">
      <h3>Our drawing &mdash; {esc(folder)}.svg</h3>
      <div class="artbox">{inline_svg(base / f"{folder}.svg", "colour")}</div>
      <div class="iconrow">
        <div class="iconcell"><div class="ic ic120">{inline_svg(base / f"{folder}-icon.svg", "icon")}</div><span>120 px</span></div>
        <div class="iconcell"><div class="ic ic24">{inline_svg(base / f"{folder}-icon.svg", "icon")}</div><span>24 px</span></div>
        <div class="iconcell"><div class="ic ic16">{inline_svg(base / f"{folder}-icon.svg", "icon")}</div>
          <span>16 px{' &mdash; breaks up' if icon16 and not icon16["legible"] else ''}</span></div>
        <div class="iconnote">icon = union silhouette of our own colour-SVG shapes,
          <code>fill:currentColor</code></div>
      </div>
    </div>
    <div class="col">
      <h3>Structured description</h3>
      <ul class="desc">{''.join(f'<li>{esc(b)}</li>' for b in summarise(d))}</ul>
      <p class="distinct">{esc(d.get("distinctive", ""))}</p>
      {''.join(f'<p class="omit"><b>Deliberately omitted:</b> {esc(x["element"])} &mdash; {esc(x["reason"])}</p>' for x in d.get("deliberately_omitted") or [])}
      <h3>Build checks</h3><ul class="checks">{checks_html}</ul>
      <h3>Originality</h3>
      <div class="orig {verdict}">
        <div class="score">{orig["max_edge_overlap"]:.3f}<span>max overlap</span></div>
        <div class="score">{(orig["control"]["p95"] if orig["control"]["p95"] is not None else 0):.3f}<span>control p95</span></div>
        <div class="score">{(margin if margin is not None else 0):+.3f}<span>margin</span></div>
        <div class="badge">{esc(orig["overall"])}</div>
      </div>
      <p class="orignote">Read the margin, not the raw score. Closest reference:
        <code>{esc(Path(orig["closest_reference"] or "-").name)}</code>.</p>
      <details><summary>Edge overlay against the closest reference</summary>{overlay}
        <p class="orignote">Dark = ours, warm = reference, magenta = coincident.</p></details>
    </div>
  </div>
  <div class="controls">
    <button class="btn approve" data-act="approve">Approve</button>
    <button class="btn regen" data-act="regenerate">Regenerate</button>
    <button class="btn reject" data-act="reject">Reject</button>
    {icon_ctrl}
    <input class="guide" type="text" placeholder="Guidance for regeneration (what to change)">
  </div>
</section>"""


CSS = """
:root{--ink:#1d2124;--mute:#666d72;--line:#dcdfe1;--bg:#f6f7f7;--card:#fff;
 --ok:#2f7d4f;--warn:#9a6b12;--bad:#a33227;--accent:#2b4a6f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
code{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;background:#eef0f1;padding:1px 4px;border-radius:3px}
header.page{background:var(--card);border-bottom:1px solid var(--line);padding:26px 32px 20px}
header.page h1{margin:0 0 10px;font-size:22px}
header.page p{margin:0 0 10px;max-width:82ch;color:#33393d}
.legal{border-left:3px solid var(--accent);padding:10px 14px;background:#f2f6fa;max-width:92ch;margin:14px 0 0}
.bar{position:sticky;top:0;z-index:10;background:var(--card);border-bottom:1px solid var(--line);
 padding:10px 32px;display:flex;gap:18px;align-items:center}
.bar .counts span{margin-right:14px;color:var(--mute)}
.bar b{color:var(--ink)}
.export{margin-left:auto;background:var(--accent);color:#fff;border:0;padding:8px 16px;
 border-radius:5px;font-size:13px;font-weight:600;cursor:pointer}
main{padding:22px 32px 60px;display:flex;flex-direction:column;gap:22px}
.row{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.row.approve{border-color:#8fbfa2}.row.reject{border-color:#d3a49e}.row.regenerate{border-color:#dcc287}
.rowhead{display:flex;align-items:center;gap:14px;padding:14px 18px;border-bottom:1px solid var(--line)}
.rowhead h2{margin:0;font-size:17px}
.sub{color:var(--mute);font-size:12.5px;margin-top:2px}
.grade{margin-left:auto;font-size:11px;font-weight:700;padding:4px 9px;border-radius:4px}
.grade.gA{background:#e2f0e8;color:var(--ok)}
.grade.gB{background:#eef1f4;color:var(--accent)}
.grade.gC{background:#f8efd9;color:var(--warn)}
.state{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;
 color:var(--mute);min-width:118px;text-align:right}
.state.approve{color:var(--ok)}.state.reject{color:var(--bad)}.state.regenerate{color:var(--warn)}
.grid{display:grid;grid-template-columns:minmax(280px,1fr) minmax(320px,1.15fr) minmax(300px,1.05fr);gap:20px;padding:18px}
.col h3{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute)}
.refstrip{display:flex;flex-wrap:wrap;gap:8px}
.ref{width:calc(50% - 4px)}
.ref img{width:100%;display:block;border:1px solid var(--line);border-radius:4px;background:#fff}
.ref.unused img{opacity:.3}
.refmeta{font-size:10.5px;color:var(--mute);margin-top:3px;line-height:1.35}
.textref a{display:flex;align-items:center;justify-content:center;height:88px;border:1px dashed var(--line);
 border-radius:4px;text-decoration:none;color:var(--mute);font-size:11px;text-align:center;background:#fafbfb}
.caveat{font-size:11.5px;color:var(--warn);margin:8px 0 0}
.share{font-size:11.5px;color:var(--accent);margin:6px 0 0}
.artbox{border:1px solid var(--line);border-radius:6px;background:#fff;padding:10px;
 display:flex;align-items:center;justify-content:center;min-height:180px}
svg.colour{width:100%;height:auto;max-height:300px;display:block}
.iconrow{display:flex;align-items:flex-end;gap:20px;margin-top:12px;flex-wrap:wrap}
.iconcell{text-align:center}.iconcell span{display:block;font-size:10px;color:var(--mute);margin-top:4px}
.iconnote{font-size:10.5px;color:var(--mute);max-width:26ch}
.ic svg.icon{width:100%;height:100%;display:block}
.ic120{width:120px;height:120px}.ic24{width:24px;height:24px}.ic16{width:16px;height:16px}
ul.desc{margin:0 0 10px;padding-left:18px}ul.desc li{margin-bottom:3px}
.distinct{margin:0 0 10px;font-style:italic;color:#3a4247}
.omit{font-size:11.5px;color:var(--warn);margin:0 0 10px}
ul.checks{margin:0 0 14px;padding-left:18px;font-size:11.5px}
ul.checks b.ok{color:var(--ok)}ul.checks b.bad{color:var(--bad)}
.orig{display:flex;align-items:center;gap:16px;padding:10px 12px;border-radius:6px;background:#f3f5f6;border:1px solid var(--line)}
.orig .score{font-size:17px;font-weight:600;font-variant-numeric:tabular-nums}
.orig .score span{display:block;font-size:9.5px;font-weight:400;color:var(--mute);text-transform:uppercase}
.orig .badge{margin-left:auto;font-size:11px;font-weight:700;padding:4px 9px;border-radius:4px}
.orig.ok .badge{background:#e2f0e8;color:var(--ok)}
.orig.warn .badge{background:#f8efd9;color:var(--warn)}
.orig.bad .badge{background:#f7e2df;color:var(--bad)}
.orignote{font-size:11px;color:var(--mute);margin:6px 0 0}
details{margin-top:8px}summary{font-size:11.5px;color:var(--accent);cursor:pointer}
img.overlay{width:100%;max-width:280px;margin-top:8px;border:1px solid var(--line);border-radius:4px}
.controls{display:flex;gap:8px;align-items:center;padding:12px 18px;border-top:1px solid var(--line);
 background:#fafbfb;flex-wrap:wrap}
.iconq{font-size:12.5px;color:#3a4247;margin-left:6px}
.btn{border:1px solid var(--line);background:#fff;padding:7px 15px;border-radius:5px;font-size:13px;cursor:pointer;font-weight:500}
.btn:hover{background:#f0f2f3}
.btn.on.approve,.btn.on.keep{background:var(--ok);border-color:var(--ok);color:#fff}
.btn.on.reject,.btn.on.drop{background:var(--bad);border-color:var(--bad);color:#fff}
.btn.on.regen{background:var(--warn);border-color:var(--warn);color:#fff}
.guide{flex:1;min-width:220px;padding:7px 10px;border:1px solid var(--line);border-radius:5px;font-size:13px}
@media (max-width:1100px){.grid{grid-template-columns:1fr}}
"""

SCRIPT = """
const KEY = "eogos-house-art-review";
const state = JSON.parse(localStorage.getItem(KEY) || "{}");
function paint(){
  const c = {approve:0, regenerate:0, reject:0}; let open = 0, icons = 0;
  document.querySelectorAll(".row").forEach(row => {
    const f = row.dataset.folder, s = state[f] || {};
    row.className = "row" + (s.decision ? " " + s.decision : "");
    const lab = row.querySelector(".state");
    lab.textContent = (s.decision || "undecided") + (s.icon ? " / icon: " + s.icon : "");
    lab.className = "state" + (s.decision ? " " + s.decision : "");
    if (s.decision) c[s.decision]++; else open++;
    if (s.icon) icons++;
    row.querySelectorAll(".btn").forEach(b => {
      const isIcon = b.dataset.act === "keep" || b.dataset.act === "drop";
      b.classList.toggle("on", isIcon ? b.dataset.act === s.icon : b.dataset.act === s.decision);
    });
    const g = row.querySelector(".guide");
    if (g && document.activeElement !== g) g.value = s.guidance || "";
  });
  document.getElementById("c-approve").textContent = c.approve;
  document.getElementById("c-regenerate").textContent = c.regenerate;
  document.getElementById("c-reject").textContent = c.reject;
  document.getElementById("c-undecided").textContent = open;
  document.getElementById("c-icon").textContent = icons;
  localStorage.setItem(KEY, JSON.stringify(state));
}
document.querySelectorAll(".row").forEach(row => {
  const f = row.dataset.folder;
  row.querySelectorAll(".btn").forEach(b => b.addEventListener("click", () => {
    const isIcon = b.dataset.act === "keep" || b.dataset.act === "drop";
    const key = isIcon ? "icon" : "decision";
    state[f] = state[f] || {};
    state[f][key] = (state[f][key] === b.dataset.act) ? null : b.dataset.act;
    if (!state[f][key]) delete state[f][key];
    paint();
  }));
  const g = row.querySelector(".guide");
  if (g) g.addEventListener("input", e => {
    state[f] = state[f] || {}; state[f].guidance = e.target.value;
    localStorage.setItem(KEY, JSON.stringify(state));
  });
});
document.getElementById("export").addEventListener("click", () => {
  const picks = [...document.querySelectorAll(".row")].map(row => {
    const f = row.dataset.folder, s = state[f] || {};
    return {folder: f, decision: s.decision || "undecided",
            icon: s.icon || null, guidance: s.guidance || ""};
  });
  const blob = new Blob([JSON.stringify({
    schema: "satellite-visuals/house-art-review/1",
    generated: new Date().toISOString(),
    source: "tools/make_art_checker.py", picks}, null, 2)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "art-picks.json"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
paint();
"""


def candidates(names=None):
    if not OUT.exists():
        return []
    found = sorted(p.name for p in OUT.iterdir()
                   if p.is_dir() and (p / "description.json").exists())
    return [n for n in found if not names or n in names]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folders", nargs="*", help="folders to include (default: all)")
    ap.add_argument("--out", default=str(PAGE))
    args = ap.parse_args(argv)

    names = candidates(set(args.folders) or None)
    if not names:
        print(f"no candidates under {OUT} — run the generation step first")
        return 1

    rows, skipped = [], []
    for folder in names:
        base = OUT / folder
        d = json.loads((base / "description.json").read_text(encoding="utf-8"))
        problems = schema.validate(d, folder)
        if problems:
            skipped.append(f"{folder}: {'; '.join(problems)}")
            continue
        orig = json.loads((base / "originality.json").read_text(encoding="utf-8"))
        chk_path = base / "checks.json"
        chk = json.loads(chk_path.read_text(encoding="utf-8")) if chk_path.exists() else {}
        icon_png = base / f"{folder}-icon-render.png"
        icon16 = art_checks.icon_legibility(icon_png) if icon_png.exists() else None
        refs_json = base / "references.json"
        refs_local = {}
        if refs_json.exists():
            for r in json.loads(refs_json.read_text(encoding="utf-8")):
                p = local_path(r)
                if p:
                    refs_local[r.get("n")] = p
        rows.append(row_html(folder, d, orig, chk, icon16, refs_local))

    for line in skipped:
        print(f"SKIP {line}")

    page = f"""<!doctype html>
<meta charset="utf-8">
<title>House artwork review</title>
<style>{CSS}</style>
<header class="page">
  <h1>House artwork review &mdash; {len(rows)} candidate{'s' if len(rows) != 1 else ''}</h1>
  <p>Each row is an <b>original drawing</b>, written from the structured description shown beside it,
  for a folder that cannot have a licensed photograph. Judge whether it reads as the right spacecraft
  and is good enough to be that mission's visual. Click any reference thumbnail to open its source
  page. Mark Approve, Regenerate (with a note) or Reject, then Export and feed the file to
  <code>tools/apply_art.py</code>.</p>
  <div class="legal"><b>Legal frame.</b> Golden rule 6 allows our own drawing of a spacecraft using
  photographs only as reference for what it looks like; a 1:1 trace of one specific render is a
  derivative and is refused. These SVGs were written as geometry from
  <code>description.json</code> &mdash; no reference raster is read, sampled, traced or embedded by
  the drawing code, and no reference file is stored in this repository. Each icon is the union
  silhouette of our own colour-SVG shapes, never of a photograph.</div>
</header>
<div class="bar">
  <div class="counts">
    <span>approved <b id="c-approve">0</b></span>
    <span>regenerate <b id="c-regenerate">0</b></span>
    <span>rejected <b id="c-reject">0</b></span>
    <span>undecided <b id="c-undecided">{len(rows)}</b></span>
    <span>icon calls <b id="c-icon">0</b></span>
  </div>
  <button class="export" id="export">Export art-picks.json</button>
</div>
<main>{''.join(rows)}</main>
<script>{SCRIPT}</script>
"""
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"OK   {len(rows)} row(s) -> {out}"
          + (f", {len(skipped)} skipped" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
