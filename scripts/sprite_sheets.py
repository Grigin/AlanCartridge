#!/usr/bin/env python3
"""Per-genre sprite-cast review sheets -> sprite_sheets/genre_<name>.png.

One labeled PNG per enabled genre: its candidate settings sorted by roll
weight (SETTING_WEIGHTS, default x1), each section showing the exact pools
ontology.roll() casts from — AVATARS (setting override or global pool),
FOES, GOODS, PROPS — drawn at 4x screen scale on that setting's real
GAME_BG colour, sprite names underneath. Pure reader: touches neither
sprites.h nor ENGINE_PROMPT.md.

  python sprite_sheets.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import spritegen as sg
from ontology import AVATARS, DISABLED_GENRES, GENRES, SETTINGS, SETTING_WEIGHTS

OUT = Path(__file__).parent / "sprite_sheets"

CELL, COLS = 64, 11                  # 4x the 16x16 screen footprint
PITCH_X, PITCH_Y = CELL + 10, CELL + 22
GUT, MARG = 80, 14                   # role-label gutter, page margin
W = MARG * 2 + GUT + COLS * PITCH_X

PAGE = (24, 24, 30)
ROLE_C = {"AVATARS": (255, 236, 39), "FOES": (255, 0, 77),
          "GOODS": (0, 228, 54), "PROPS": (194, 195, 199)}


def _font(size):
    for p in ("/System/Library/Fonts/Menlo.ttc",
              "/System/Library/Fonts/Monaco.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


F_LBL, F_ROLE, F_SET, F_TITLE, F_SUB = (_font(s) for s in (9, 12, 15, 24, 11))


def load_sprites():
    sheets = {k: Image.open(p).convert("RGBA")
              for k, (kind, p, _) in sg.SOURCES.items() if kind != "file16"}
    px = {}
    for entries in sg.CATALOG.values():
        for e in entries:
            size, nib = sg.load_entry(e, sheets)
            px[f"SPR_{e[-2]}"] = (size, nib)
    return px


def blit(d, px, name, x, y, bg):
    size, nib = px[name]
    s = CELL // size
    d.rectangle([x - 1, y - 1, x + CELL, y + CELL], outline=(70, 70, 84), fill=bg)
    for j, n in enumerate(nib):
        if n == sg.TRANSP:
            continue
        cx, cy = x + (j % size) * s, y + (j // size) * s
        d.rectangle([cx, cy, cx + s - 1, cy + s - 1], fill=sg.PICO[n])


def row_block(d, px, names, role, note, y, bg):
    d.text((MARG, y + 4), role, font=F_ROLE, fill=ROLE_C.get(role, (170, 170, 185)))
    if note:
        d.text((MARG, y + 20), note, font=F_LBL, fill=(130, 130, 145))
    for i, n in enumerate(names):
        x = MARG + GUT + (i % COLS) * PITCH_X
        yy = y + (i // COLS) * PITCH_Y
        blit(d, px, n, x, yy, bg)
        lbl = n[4:]
        tw = d.textlength(lbl, font=F_LBL)
        d.text((x + (CELL - tw) / 2, yy + CELL + 3), lbl,
               font=F_LBL, fill=(205, 205, 215))
    return y + math.ceil(len(names) / COLS) * PITCH_Y + 6


def setting_section(d, px, genre, sname, y):
    kit = SETTINGS[sname]
    w = SETTING_WEIGHTS.get(genre, {}).get(sname, 1)
    bg = sg.PICO[kit["bg"][0]]
    d.text((MARG, y), sname.upper(), font=F_SET, fill=(255, 241, 232))
    tx = MARG + d.textlength(sname.upper(), font=F_SET) + 10
    d.text((tx, y + 3), f"x{w}", font=F_ROLE,
           fill=(255, 236, 39) if w > 1 else (110, 110, 125))
    cx = tx + 42
    for label, ids in (("bg", kit["bg"]), ("accents", kit["accents"])):
        d.text((cx, y + 4), label, font=F_LBL, fill=(130, 130, 145))
        cx += d.textlength(label, font=F_LBL) + 5
        for i in ids:
            d.rectangle([cx, y + 2, cx + 13, y + 15],
                        fill=sg.PICO[i], outline=(70, 70, 84))
            cx += 17
        cx += 10
    y += 26
    avs = kit.get("avatars")
    y = row_block(d, px, avs or AVATARS, "AVATARS",
                  "override" if avs else "global", y, bg)
    for role in ("foes", "goods", "props"):
        y = row_block(d, px, kit[role], role.upper(), None, y, bg)
    return y + 8


def genre_sheet(genre, px):
    weights = SETTING_WEIGHTS.get(genre, {})
    order = sorted(SETTINGS, key=lambda s: -weights.get(s, 1))
    im = Image.new("RGB", (W, 9000), PAGE)
    d = ImageDraw.Draw(im)
    y = MARG
    d.text((MARG, y), genre.upper(), font=F_TITLE, fill=(255, 241, 232))
    if weights:
        odds = " · ".join(f"{s} x{n}" for s, n in
                          sorted(weights.items(), key=lambda kv: -kv[1]))
        odds += " · others x1"
    else:
        odds = "all settings equally likely"
    d.text((MARG, y + 32),
           f"setting odds: {odds}   —   cells sit on each setting's GAME_BG",
           font=F_SUB, fill=(150, 150, 165))
    y += 56
    for sname in order:
        d.line([(MARG, y), (W - MARG, y)], fill=(45, 45, 56))
        y = setting_section(d, px, genre, sname, y + 8)
    d.text((MARG, y),
           "wildcards may borrow foes/goods from any other setting (guests/"
           "blend) or cast a foe as the avatar (swap)",
           font=F_SUB, fill=(120, 120, 135))
    im.crop((0, 0, W, y + 22)).save(OUT / f"genre_{genre}.png")
    print(f"wrote sprite_sheets/genre_{genre}.png ({y + 22}px tall)")


def unkitted_sheet(px):
    """Catalog sprites cast by no kit: games can still draw them by name, but
    skin never casts them — keep them visible so they aren't lost in reviews."""
    used = set(AVATARS)
    for kit in SETTINGS.values():
        for role in ("props", "foes", "goods"):
            used.update(kit[role])
        used.update(kit.get("avatars", []))
    ANIM = {"people", "beasts", "monsters"}
    im = Image.new("RGB", (W, 9000), PAGE)
    d = ImageDraw.Draw(im)
    y = MARG
    d.text((MARG, y), "NOT CAST BY ANY KIT", font=F_TITLE, fill=(255, 241, 232))
    d.text((MARG, y + 32),
           "in the catalog (games may draw these by name) but no setting casts them",
           font=F_SUB, fill=(150, 150, 165))
    y += 56
    for grp, entries in sg.CATALOG.items():
        have = {f"SPR_{e[-2]}" for e in entries}
        names = []
        for e in entries:
            n = f"SPR_{e[-2]}"
            if n in used:
                continue
            if grp in ANIM and n.endswith("2") and n[:-1] in have:
                continue                      # anim frame 2: rides its base
            names.append(n)
        if not names:
            continue
        d.line([(MARG, y), (W - MARG, y)], fill=(45, 45, 56))
        y = row_block(d, px, names, grp.upper(), None, y + 8, (45, 45, 56))
    im.crop((0, 0, W, y + 12)).save(OUT / "_unkitted.png")
    print(f"wrote sprite_sheets/_unkitted.png ({y + 12}px tall)")


def main():
    OUT.mkdir(exist_ok=True)
    px = load_sprites()
    for g in GENRES:
        if g in DISABLED_GENRES:
            print(f"skip {g} (disabled)")
            continue
        genre_sheet(g, px)
    unkitted_sheet(px)


if __name__ == "__main__":
    main()
