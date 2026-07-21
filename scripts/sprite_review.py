"""Generate sprite_review.html — a click-to-curate GUI over every assets/ pack.

  python sprite_review.py     then:  open sprite_review.html

Every tile/file in assets/ is shown; tiles already named in spritegen.CATALOG
render muted with their SPR_ name. Click tiles to select, Export downloads
sprite_selection.json (keys match spritegen's source coordinates, so the
selection can be ingested into CATALOG directly). Selection persists in the
browser's localStorage between sessions.
"""
import base64
import html
import io
import json
from pathlib import Path

from PIL import Image

import spritegen as sg

ROOT = Path(__file__).parent
OUT = ROOT / "sprite_review.html"
ICONS = ROOT / "assets/kenney_game-icons-expansion/PNG"


def b64(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def catalog_names():
    d = {}
    for entries in sg.CATALOG.values():
        for e in entries:
            src = e[0]
            if src == "CTC":                  # composite: mute the whole region
                col, row, w, h = e[1:5]
                for dc in range(w):
                    for dr in range(h):
                        d[("CT", col + dc, row + dr)] = e[-2]
                continue
            if src == "XF":                   # loose-pack rect crop
                pack, file = e[1].split("/", 1)
                d[(f"X:{pack}", file, e[2], e[3], e[4], e[5])] = e[-2]
                continue
            key = (src, e[1]) if sg.SOURCES[src][0] == "file16" else (src, e[1], e[2])
            d[key] = e[-2]
    return d


def grid_tiles(src, path, tile):
    im = Image.open(path).convert("RGBA")
    cols, rows = im.width // tile, im.height // tile
    for r in range(rows):
        for c in range(cols):
            cell = im.crop((c * tile, r * tile, (c + 1) * tile, (r + 1) * tile))
            if cell.getextrema()[3][1] < 16:      # fully transparent -> skip
                continue
            yield {"src": src, "col": c, "row": r}, cell, f"{c},{r}"


def file_tiles(src, base, box=32):
    for p in sorted(base.rglob("*.png")):
        im = Image.open(p).convert("RGBA")
        sc = min(box / im.width, box / im.height, 1.0)
        im = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))),
                       Image.BOX)
        yield {"src": src, "file": str(p.relative_to(base))}, im, p.stem


# ── auto-slicing for loose packs (no known grid) ────────────────────────────

def _bands(alpha, axis):
    """Runs of content rows (axis=1) or cols (axis=0) in an alpha channel."""
    proj = alpha.resize((1, alpha.height) if axis else (alpha.width, 1), Image.BOX)
    data = list(proj.getdata())
    bands, start = [], None
    for i, v in enumerate(data):
        if v > 0 and start is None:
            start = i
        elif v == 0 and start is not None:
            bands.append((start, i)); start = None
    if start is not None:
        bands.append((start, len(data)))
    return bands


def sliced_regions(im):
    """Content cells split on fully-transparent gutters: rows, columns, then
    one refinement pass of rows within each cell (handles gutterless axes)."""
    a = im.getchannel("A")
    for y0, y1 in _bands(a, axis=1):
        row = im.crop((0, y0, im.width, y1))
        for x0, x1 in _bands(row.getchannel("A"), axis=0):
            cell = im.crop((x0, y0, x1, y1))
            subs = _bands(cell.getchannel("A"), axis=1)
            if len(subs) > 1:
                for sy0, sy1 in subs:
                    yield (x0, y0 + sy0, x1 - x0, sy1 - sy0)
            else:
                yield (x0, y0, x1 - x0, y1 - y0)


def grid_guess(w, h):
    for t in (48, 40, 32, 28, 24, 20, 16, 8):
        if w % t == 0 and h % t == 0:
            return t
    return 16


def grid_rects(im):
    t = grid_guess(*im.size)
    return [(c * t, r * t, t, t)
            for r in range(im.height // t) for c in range(im.width // t)]


def loose_tiles(pack_dir, box=64):
    """Cells for every PNG in a loose pack; keys carry exact pixel rects."""
    src = f"X:{pack_dir.name}"
    for p in sorted(pack_dir.rglob("*.png")):
        if any(s in p.name.lower() for s in ("mockup", "_black", "preview")):
            continue
        im = Image.open(p).convert("RGBA")
        rel = str(p.relative_to(pack_dir))
        has_alpha = im.getextrema()[3][0] < 128
        rects = list(sliced_regions(im)) if has_alpha else grid_rects(im)
        if len(rects) <= 1 and im.width * im.height > 64 * 64:
            rects = grid_rects(im)            # gutterless packed tileset
        for (x, y, w, h) in rects:
            if w < 4 or h < 4:                # specks / stray pixels
                continue
            cell = im.crop((x, y, x + w, y + h))
            ext = cell.getextrema()
            if ext[3][1] < 16:                # fully transparent
                continue
            if all(lo == hi for lo, hi in ext[:3]) and ext[3][0] == ext[3][1]:
                continue                      # flat single-color cell (opaque bg)
            sc = min(box / w, box / h, 2.0)
            thumb = cell.resize((max(1, round(w * sc)), max(1, round(h * sc))),
                                Image.NEAREST)
            yield ({"src": src, "file": rel, "x": x, "y": y, "w": w, "h": h},
                   thumb, f"{w}x{h}@{x},{y}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-only", action="store_true",
                    help="review only loose packs not wired into spritegen; "
                         "writes sprite_review_new.html")
    args = ap.parse_args()

    names = catalog_names()
    sections = []
    total = muted = 0

    KNOWN = {"kenney_micro-roguelike", "kenney_pico-8-platformer", "Paper-Pixels-8x8",
             "kenney_roguelike-modern-city", "kenney_racing-pack",
             "kenney_game-icons-expansion"}
    datasets = []
    if not args.new_only:
        for src, (kind, path, _) in sg.SOURCES.items():
            if kind == "file16":
                datasets.append((f"{src} · {path.parent.name} (files)", src,
                                 file_tiles(src, path)))
            else:
                tile = 8 if kind == "grid8" else 16
                datasets.append((f"{src} · {path.parent.parent.name}/{path.name}", src,
                                 grid_tiles(src, path, tile)))
        icon_dir = next((ICONS / v for v in ("Colored", "White", "Black")
                         if (ICONS / v).is_dir()), None)
        if icon_dir and "GI" not in sg.SOURCES:   # skip if already a real source
            datasets.append((f"GI · game-icons/{icon_dir.name} (files)", "GI",
                             file_tiles("GI", icon_dir)))
    for d in sorted((ROOT / "assets").iterdir()):
        if d.is_dir() and d.name not in KNOWN:
            datasets.append((f"NEW · {d.name} (auto-sliced)", f"X:{d.name}",
                             loose_tiles(d)))

    for label, src, tiles in datasets:
        cells = []
        n = m = 0
        for key, im, cap in tiles:
            n += 1
            k = ((key["src"], key["file"], key["x"], key["y"], key["w"], key["h"])
                 if "x" in key
                 else (key["src"], key["file"]) if "file" in key
                 else (key["src"], key["col"], key["row"]))
            spr = names.get(k)
            if spr:
                m += 1
            cls = "tile muted" if spr else "tile"
            tip = html.escape(f"SPR_{spr}" if spr else cap)
            dk = html.escape(json.dumps(key), quote=True)   # survives ' in names
            cells.append(
                f'<div class="{cls}" data-key="{dk}" title="{tip}">'
                f'<img style="--nat:{im.width}" '
                f'src="data:image/png;base64,{b64(im)}">'
                f'<span>{html.escape(spr or cap)}</span></div>')
        total += n
        muted += m
        sections.append(
            f'<details open><summary>{html.escape(label)} — {n} tiles, '
            f'{m} already in catalog</summary><div class="grid">'
            + "".join(cells) + "</div></details>")
        print(f"{label}: {n} tiles ({m} in catalog)")

    page = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>AlanCartridge sprite review</title><style>
:root { --zoom: 5; }
body { background:#1c1c24; color:#eee; font:14px system-ui; margin:0; }
header { position:sticky; top:0; background:#12121a; padding:10px 16px;
  display:flex; gap:16px; align-items:center; z-index:9; }
header b { color:#ffd24a; }
button { background:#ffd24a; border:0; padding:8px 14px; border-radius:6px;
  font-weight:700; cursor:pointer; }
button.ghost { background:#333; color:#ccc; }
details { margin:10px 16px; }
summary { cursor:pointer; padding:6px 0; color:#9ecbff; font-weight:600; }
.grid { display:flex; flex-wrap:wrap; gap:8px; padding:8px 0; }
.tile { background:#2a2a34; border:2px solid #2a2a34; border-radius:6px;
  padding:4px; text-align:center; cursor:pointer; }
.tile img { image-rendering: pixelated; display:block; margin:0 auto;
  width: calc(var(--nat) * var(--zoom) * 1px); }
.tile span { display:block; font-size:10px; color:#888; max-width:96px;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tile.sel { border-color:#ffd24a; background:#3a3320; }
.tile.sel span { color:#ffd24a; }
.tile.muted { opacity:.35; cursor:default; }
.tile.muted span { color:#6f6; }
</style></head><body>
<header>
  <b>__TOTAL__ tiles</b> · __MUTED__ in catalog ·
  <b id="count">0</b>&nbsp;selected
  <button id="export">Export JSON</button>
  <button class="ghost" id="clear">Clear</button>
  <label>zoom <input id="zoom" type="range" min="2" max="10" value="5"></label>
</header>
__SECTIONS__
<script>
const sel = new Set(JSON.parse(localStorage.getItem("spriteSel") || "[]")
  .filter(s => { try { JSON.parse(s); return true; } catch { return false; } }));
const count = document.getElementById("count");
function sync() {
  count.textContent = sel.size;
  localStorage.setItem("spriteSel", JSON.stringify([...sel]));
}
document.querySelectorAll(".tile").forEach(t => {
  const k = t.dataset.key;
  if (sel.has(k)) t.classList.add("sel");
  if (t.classList.contains("muted")) return;
  t.addEventListener("click", () => {
    t.classList.toggle("sel");
    t.classList.contains("sel") ? sel.add(k) : sel.delete(k);
    sync();
  });
});
sync();
document.getElementById("zoom").addEventListener("input", e =>
  document.documentElement.style.setProperty("--zoom", e.target.value));
document.getElementById("clear").addEventListener("click", () => {
  sel.clear();
  document.querySelectorAll(".tile.sel").forEach(t => t.classList.remove("sel"));
  sync();
});
document.getElementById("export").addEventListener("click", () => {
  const out = { selected: [...sel].map(JSON.parse) };
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)],
                                        { type: "application/json" }));
  a.download = "sprite_selection.json";
  a.click();
});
</script></body></html>"""
    page = (page.replace("__TOTAL__", str(total))
                .replace("__MUTED__", str(muted))
                .replace("__SECTIONS__", "\n".join(sections)))
    out = ROOT / "sprite_review_new.html" if args.new_only else OUT
    out.write_text(page)
    print(f"\nwrote {out} ({out.stat().st_size // 1024} KB, {total} tiles, "
          f"{muted} muted) — open it in a browser")


if __name__ == "__main__":
    main()
