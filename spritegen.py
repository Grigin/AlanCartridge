"""Bake sprites from assets/ into sprites.h + the prompt catalog in ENGINE_PROMPT.md.
Two banks:
  8x8 bank  (grid8 sources)  — drawn 2x by the engine (16x16 on screen)
  16x16 bank (grid16/file16) — drawn 1x (same footprint, 4x the detail);
  ids >= SPR16_BASE. 4bpp PAL index, high nibble = left pixel, nibble 0 =
  transparent (near-black maps to navy 1, the PICO-8 idiom).

Racing files are one sprite per named PNG, box-fit into 16x16; vehicles rotated to face right.
"""
import argparse
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
OUT_H = ROOT / "forge_sketch" / "sprites.h"
PROMPT = ROOT / "ENGINE_PROMPT.md"
A = ROOT / "assets"

# PICO-8 palette, canonical RGB — indices match PAL[] in engine.h
PICO = [(0x00, 0x00, 0x00), (0x1D, 0x2B, 0x53), (0x7E, 0x25, 0x53), (0x00, 0x87, 0x51),
        (0xAB, 0x52, 0x36), (0x5F, 0x57, 0x4F), (0xC2, 0xC3, 0xC7), (0xFF, 0xF1, 0xE8),
        (0xFF, 0x00, 0x4D), (0xFF, 0xA3, 0x00), (0xFF, 0xEC, 0x27), (0x00, 0xE4, 0x36),
        (0x29, 0xAD, 0xFF), (0x83, 0x76, 0x9C), (0xFF, 0x77, 0xA8), (0xFF, 0xCC, 0xAA)]
TRANSP = 0

CMAP = {  # exact source-color -> PAL index (MR/P8 fully hand-mapped)
 "MR": {0x222323: 1, 0x3CA370: 3, 0x3D6E70: 3, 0x43434F: 1, 0x5DDE87: 11,
        0x606070: 5, 0x6476E8: 12, 0x7E7E8F: 13, 0x86A7ED: 12, 0x8C3F5D: 2,
        0xBA6156: 4, 0xC2C2D1: 6, 0xEB564B: 8, 0xF2A65E: 9, 0xFF9166: 9,
        0xFFB570: 15, 0xFFB5B5: 14, 0xFFE478: 10, 0xFFFFEB: 7},
 "P8": {0x000000: 1, 0x1D2B53: 1, 0x7E2553: 2, 0xAB5236: 4, 0x5F574F: 5,
        0xC2C3C7: 6, 0xFFF1E8: 7, 0xFF004D: 8, 0xFFA300: 9, 0x29ADFF: 12,
        0x83769C: 13, 0xFF77A8: 14},
}
OVERRIDE = {  # per-source fixups on top of nearest-PICO for auto sources
 "PP": {0xCC5C5C: 8, 0xD66464: 8, 0xE77373: 8,          # salmon reds -> red
        0xEB9470: 9, 0xDC7F6B: 9, 0xD68667: 9, 0xEA8871: 9,  # worm oranges
        0x7789BE: 12, 0x7894BF: 12, 0x8098DF: 12,       # soft blues -> sky
        0x829CE8: 12, 0x93A9EB: 12},
 "CT": {},
 "RC": {0xE86A17: 8, 0xD96417: 4, 0x9F4910: 4},          # "red" livery -> red
}

SOURCES = {
 "MR":  ("grid8", A / "kenney_micro-roguelike/Tilemap/colored_tilemap_packed.png", "MR"),
 "P8":  ("grid8", A / "kenney_pico-8-platformer/Transparent/Tilemap/tilemap_packed.png", "P8"),
 "PPP": ("grid8", A / "Paper-Pixels-8x8/no-shadow/Player.png", "PP"),
 "PPE": ("grid8", A / "Paper-Pixels-8x8/no-shadow/Enemies.png", "PP"),
 "PPC": ("grid8", A / "Paper-Pixels-8x8/no-shadow/Collectables.png", "PP"),
 "PPT": ("grid8", A / "Paper-Pixels-8x8/no-shadow/Tiles.png", "PP"),
 "CT":  ("grid16", A / "kenney_roguelike-modern-city/Tilemap/tilemap_packed.png", "CT"),
 "RC":  ("file16", A / "kenney_racing-pack/PNG", "RC"),
}
ROTATE = ("Cars/", "Motorcycles/")   # racing subdirs whose sprites face right

# ── catalog: topic groups; entry = (src, col,row | relpath, NAME, description)
CATALOG = {
 "people": [
  ("MR", 4, 0, "VIKING", "horned warrior"), ("MR", 5, 0, "DWARF", "helmed dwarf"),
  ("MR", 6, 0, "KNIGHT", "armored knight"), ("MR", 7, 0, "HUNTER", "green hunter"),
  ("MR", 8, 0, "MONK", "bald monk"), ("MR", 9, 0, "BRUTE", "horned brute"),
  ("MR", 10, 0, "GUARD", "full-plate guard"), ("MR", 11, 0, "ELF", "green-haired elf"),
  ("MR", 12, 0, "IMP", "red imp"), ("MR", 13, 0, "CYCLOPS", "one-eyed brute"),
  ("MR", 14, 0, "WIZARD", "hatted wizard"),
  ("PPP", 0, 2, "GUNNER", "runner with pistol"), ("PPP", 2, 2, "GUNNER2", "gunner frame 2"),
  ("PPP", 0, 21, "COMMANDO", "runner with rifle"), ("PPP", 2, 21, "COMMANDO2", "commando frame 2")],
 "beasts": [
  ("MR", 4, 1, "SNAKE", "coiled snake"), ("MR", 5, 1, "FOX", "fox"),
  ("MR", 6, 1, "BUNNY", "white bunny"), ("MR", 7, 1, "SPIDER", "spider"),
  ("MR", 9, 1, "BAT", "winged bat/moth"), ("MR", 10, 1, "TURTLE", "green turtle"),
  ("MR", 11, 1, "CRAB", "crab"),
  ("PPE", 5, 13, "CHICK", "white chicken"), ("PPE", 6, 13, "CHICK2", "chicken frame 2"),
  ("PPE", 4, 15, "TOAD", "brown toad"), ("PPE", 4, 20, "PENGUIN", "grey penguin")],
 "monsters": [
  ("MR", 8, 1, "SLIME", "gooey blob"), ("MR", 12, 1, "GOBLIN", "capped goblin"),
  ("MR", 14, 1, "GHOST", "ghost"),
  ("P8", 0, 6, "HOPPER", "red hopper"), ("P8", 1, 6, "HOPPER2", "hopper frame 2"),
  ("P8", 4, 6, "BLOB", "grinning blob"), ("P8", 7, 6, "PUFF", "round puffball"),
  ("P8", 8, 6, "WISP", "sparkle wisp"), ("P8", 0, 7, "JELLY", "blue jelly"),
  ("P8", 1, 7, "JELLY2", "jelly frame 2"), ("P8", 4, 7, "CUBE", "glaring cube"),
  ("P8", 5, 7, "MITE", "tiny mite"), ("P8", 7, 7, "SHADE", "dark shade"),
  ("P8", 8, 7, "SHADE2", "shade frame 2"),
  ("PPE", 4, 2, "DRONE", "striped hover-drone"),
  ("PPE", 6, 3, "SHROOM", "red walking shroom"), ("PPE", 7, 3, "SHROOM2", "shroom frame 2"),
  ("PPE", 6, 4, "TOADSTOOL", "purple shroom"),
  ("PPE", 4, 5, "WORM", "orange worm"), ("PPE", 6, 5, "WORM2", "worm frame 2"),
  ("PPE", 4, 6, "WORMPINK", "pink worm"),
  ("PPE", 4, 7, "DROPLET", "blue drip critter"), ("PPE", 5, 9, "GLOB", "purple drip critter"),
  ("PPE", 5, 12, "SPIKERAT", "spiny rat"),
  ("PPE", 5, 14, "BATTY", "purple bat"), ("PPE", 6, 14, "BATTY2", "batty frame 2"),
  ("PPE", 4, 16, "SNOWMAN", "small snowman")],
 "vehicles": [
  ("RC", "Cars/car_red_1.png", "CAR_RED", "red race car"),
  ("RC", "Cars/car_blue_1.png", "CAR_BLUE", "blue race car"),
  ("RC", "Cars/car_green_1.png", "CAR_GREEN", "green race car"),
  ("RC", "Cars/car_yellow_1.png", "CAR_YELLOW", "yellow race car"),
  ("RC", "Cars/car_black_1.png", "CAR_BLACK", "black race car"),
  ("RC", "Motorcycles/motorcycle_red.png", "MOTO_RED", "red motorcycle"),
  ("RC", "Motorcycles/motorcycle_green.png", "MOTO_GREEN", "green motorcycle"),
  ("RC", "Objects/cone_straight.png", "CONE", "traffic cone"),
  ("RC", "Objects/barrel_red.png", "BARREL_RED", "red barrel"),
  ("RC", "Objects/barrel_blue.png", "BARREL_BLUE", "blue barrel"),
  ("RC", "Objects/barrier_red_race.png", "BARRIER_RED", "red-white barrier"),
  ("RC", "Objects/barrier_white_race.png", "BARRIER_WHT", "white barrier"),
  ("RC", "Objects/arrow_yellow.png", "CHEVRON", "yellow chevron sign"),
  ("RC", "Objects/oil.png", "OILSLICK", "oil slick"),
  ("RC", "Objects/rock1.png", "ROCK", "grey rock"),
  ("RC", "Objects/rock2.png", "ROCK2", "pale rock"),
  ("RC", "Objects/tires_red.png", "TIRES_RED", "red tire ring"),
  ("RC", "Objects/tires_white.png", "TIRES_WHT", "white tire ring"),
  ("RC", "Objects/tree_large.png", "PARKTREE", "round road tree")],
 "weapons": [
  ("MR", 6, 4, "SWORD", "sword"), ("MR", 7, 4, "PICKAXE", "pickaxe"),
  ("MR", 8, 4, "BOW", "bow and arrow"), ("MR", 9, 4, "SPEAR", "gold spear"),
  ("MR", 10, 4, "HAMMER", "war hammer"), ("MR", 10, 3, "AXE", "axe"),
  ("PPC", 0, 1, "PISTOL", "grey pistol"), ("PPC", 2, 1, "AMMO", "three bullets")],
 "items": [
  ("MR", 8, 5, "SUN", "sun / fireball"), ("MR", 9, 5, "RING", "ring"),
  ("MR", 10, 5, "KEY", "key"), ("MR", 11, 5, "LADDER", "ladder"),
  ("MR", 4, 6, "HEART_EMPTY", "empty heart"), ("MR", 5, 6, "HEART_HALF", "half heart"),
  ("MR", 6, 6, "HEART", "full heart"), ("MR", 10, 6, "SHIELD", "bronze shield"),
  ("MR", 3, 7, "ARROW", "big right arrow"), ("MR", 7, 8, "POTION", "potion flask"),
  ("MR", 7, 2, "LOCK", "padlock"), ("MR", 10, 7, "BELL", "bronze bell"),
  ("MR", 2, 8, "HOOP", "gold hoop"), ("MR", 0, 7, "AMULET", "square amulet"),
  ("MR", 4, 3, "BOOTS", "boots"),
  ("P8", 13, 5, "GEM", "gem"), ("P8", 12, 9, "STAR", "star"),
  ("P8", 14, 5, "MAGNET", "red magnet"),
  ("PPC", 1, 0, "COIN", "gold coin"), ("PPC", 2, 0, "BLUEGEM", "blue gem")],
 "nature": [
  ("MR", 5, 4, "SPROUT", "grass sprouts"), ("MR", 4, 5, "TREE", "round tree"),
  ("MR", 5, 5, "PINE", "pine tree"), ("MR", 6, 5, "BUSH", "bushes"),
  ("MR", 7, 5, "PALM", "palm tree"), ("P8", 6, 5, "CLOUD", "cloud"),
  ("PPT", 1, 8, "FLOWER", "small flower"),
  ("CT", 33, 11, "CITYTREE", "green street tree"), ("CT", 32, 12, "AUTUMN", "orange street tree")],
 "buildings": [
  ("MR", 4, 2, "DOOR", "closed door"), ("MR", 5, 2, "DOOR_OPEN", "open door"),
  ("MR", 4, 7, "SIGN", "sign post"), ("MR", 5, 7, "HOUSE", "house"),
  ("MR", 6, 7, "CASTLE", "castle"), ("MR", 7, 7, "TOWER", "tower"),
  ("MR", 15, 1, "FLAG", "red banner"), ("MR", 15, 2, "PENNANT", "red pennant"),
  ("CT", 1, 7, "BRICKWALL", "red brick wall"), ("CT", 5, 7, "WALLPANEL", "grey wall"),
  ("CT", 13, 7, "STOREFRONT", "glass storefront"),
  ("CT", 13, 4, "AWNING", "green awning"), ("CT", 24, 9, "CANOPY", "striped canopy"),
  ("CT", 20, 26, "DOOR_BROWN", "brown city door"), ("CT", 23, 26, "DOOR_GREEN", "green city door"),
  ("CT", 26, 26, "DOOR_ORANGE", "orange city door"),
  ("CT", 32, 4, "BILLBOARD", "green billboard"), ("CT", 35, 5, "BILLBOARD_T", "teal billboard"),
  ("CT", 33, 7, "BILLBOARD_O", "orange billboard"), ("CT", 36, 7, "NEON", "teal neon sign")],
 "urban": [
  ("CT", 15, 14, "HYDRANT", "orange hydrant"), ("CT", 2, 16, "STREETLAMP", "street lamp"),
  ("CT", 12, 16, "MAILBOX", "teal mailbox"), ("CT", 17, 15, "BENCH", "wooden bench"),
  ("CT", 25, 6, "BARRICADE", "striped barricade"), ("CT", 24, 8, "VENDING", "teal vending machine"),
  ("CT", 29, 7, "GASPUMP", "gas pump"), ("CT", 35, 9, "BOLLARD", "light bollard"),
  ("CT", 19, 13, "PARKMETER", "parking meter"), ("CT", 34, 14, "PARASOL", "market umbrella"),
  ("CT", 2, 13, "FUSEBOX", "electric panel"), ("CT", 1, 13, "ACUNIT", "AC unit"),
  ("CT", 5, 13, "LAUNDRY", "clothesline shirt"), ("CT", 13, 13, "TRASHBAG", "trash bag"),
  ("CT", 17, 13, "BIN", "trash can"), ("CT", 13, 14, "TIRESTACK", "tire stack"),
  ("CT", 13, 16, "CARTON", "cardboard box"), ("CT", 16, 17, "CHAINLINK", "chain-link fence"),
  ("CT", 10, 18, "FRUITSTAND", "fruit stand"), ("CT", 11, 18, "VEGSTAND", "veggie stand"),
  ("CT", 0, 16, "LOCKER", "green locker"), ("CT", 30, 3, "OILDRUM", "steel drum"),
  ("CT", 31, 3, "KEG", "pale keg"), ("CT", 29, 6, "DECKCHAIR", "pool chair"),
  ("CT", 28, 5, "POOL", "pool water"), ("CT", 19, 24, "ROADARROW", "painted road arrow")],
 "furniture": [
  ("MR", 8, 2, "POT", "pot"), ("MR", 9, 2, "URN", "dark urn"),
  ("MR", 9, 3, "CRATE", "crate"), ("MR", 10, 2, "STATUE", "grey statue"),
  ("MR", 8, 7, "CROSS", "grave cross"), ("MR", 9, 7, "GRAVE", "tombstone"),
  ("MR", 11, 6, "WELL", "water well"), ("MR", 13, 4, "PILLAR", "stone pillar"),
  ("MR", 6, 3, "TABLE", "wooden table"), ("MR", 8, 3, "STOOL", "stool"),
  ("MR", 13, 5, "THRONE", "dark throne"), ("MR", 3, 5, "DRESSER", "drawer chest"),
  ("MR", 11, 4, "GATE", "double door"), ("MR", 7, 9, "FURNACE", "stone furnace"),
  ("MR", 13, 1, "BUST", "armor bust")],
 "terrain": [
  ("MR", 15, 6, "WATER", "water tile"), ("MR", 2, 1, "BLOCKX", "X-marked block"),
  ("MR", 12, 3, "CHECKFLOOR", "dark checker floor"),
  ("P8", 0, 2, "SPRING", "spring coil"), ("P8", 0, 4, "PLATFORM", "platform pad"),
  ("P8", 0, 5, "SPIKES", "floor spikes"), ("P8", 1, 5, "CHECKER", "checker block"),
  ("P8", 2, 1, "BLOCKGREY", "speckled block"), ("P8", 3, 4, "BLOCKGOLD", "gold block"),
  ("P8", 10, 4, "BLOCKPINK", "pink block"),
  ("CT", 1, 20, "SIDEWALK", "pavement"), ("CT", 16, 22, "ASPHALT", "dark asphalt"),
  ("CT", 12, 21, "LANELINE", "yellow lane line"), ("CT", 13, 22, "CROSSWALK", "zebra crossing"),
  ("CT", 9, 24, "MANHOLE", "manhole cover"), ("CT", 15, 19, "GRATE", "hatched steel plate"),
  ("CT", 1, 26, "GRASS", "grass block"), ("CT", 10, 26, "DIRT", "dirt block"),
  ("CT", 33, 1, "LAWN", "park lawn")],
 "fx": [
  ("MR", 0, 8, "ORB", "magic orb"), ("MR", 1, 8, "PORTAL", "green swirl"),
  ("MR", 3, 8, "BOOM", "explosion burst"), ("MR", 4, 8, "SPARK", "sparkles"),
  ("MR", 5, 8, "BOLT", "bolt streak"), ("MR", 6, 8, "FIREBOLT", "fire streak"),
  ("MR", 8, 8, "FIRE", "campfire"), ("MR", 9, 8, "CANDLE", "candle"),
  ("MR", 10, 8, "FLAME", "small flame"), ("P8", 8, 5, "ZAP", "blue lightning")],
}


def map_color(src, rgb):
    if src in CMAP:
        if rgb not in CMAP[src]:
            raise SystemExit(f"unmapped color #{rgb:06X} in hand-mapped source {src}")
        return CMAP[src][rgb]
    ov = OVERRIDE.get(src, {})
    if rgb in ov:
        return ov[rgb]
    r, g, b = rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255
    return min(range(1, 16),
               key=lambda i: (r - PICO[i][0]) ** 2 + (g - PICO[i][1]) ** 2 + (b - PICO[i][2]) ** 2)


def nib_from_img(img, src, x0, y0, size):
    out = []
    for y in range(size):
        for x in range(size):
            r, g, b, a = img.getpixel((x0 + x, y0 + y))
            out.append(TRANSP if a < 128 else map_color(src, (r << 16) | (g << 8) | b))
    return out


def tile16_from_file(path, src, rotate):
    im = Image.open(path).convert("RGBA")
    if rotate:
        im = im.transpose(Image.ROTATE_270)
    w, h = im.size
    sc = min(16 / w, 16 / h)
    nw, nh = max(1, round(w * sc)), max(1, round(h * sc))
    im = im.resize((nw, nh), Image.NEAREST)   # keep flat colors exact for overrides
    tile = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    tile.alpha_composite(im, ((16 - nw) // 2, (16 - nh) // 2))
    return nib_from_img(tile, src, 0, 0, 16)


def load_entry(entry, sheets):
    src = entry[0]
    kind, path, cmsrc = SOURCES[src]
    if kind == "file16":
        rel = entry[1]
        return 16, tile16_from_file(path / rel, cmsrc, any(rel.startswith(p) for p in ROTATE))
    col, row = entry[1], entry[2]
    size = 8 if kind == "grid8" else 16
    return size, nib_from_img(sheets[src], cmsrc, col * size, row * size, size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", help="contact sheet PNG prefix (writes PREFIX_8/PREFIX_16)")
    args = ap.parse_args()

    sheets = {k: Image.open(p).convert("RGBA")
              for k, (kind, p, _) in SOURCES.items() if kind != "file16"}

    flat = []
    for grp, entries in CATALOG.items():
        for e in entries:
            size, nib = load_entry(e, sheets)
            flat.append({"group": grp, "name": e[-2], "desc": e[-1], "size": size, "nib": nib})
    names = [f["name"] for f in flat]
    assert len(names) == len(set(names)), "duplicate sprite name"

    b8 = [f for f in flat if f["size"] == 8]
    b16 = [f for f in flat if f["size"] == 16]
    order = b8 + b16                      # ids: all 8x8 first, then 16x16
    enum = [f"SPR_{f['name']}={i}" for i, f in enumerate(order)]

    def pack(nib):
        return [(nib[j] << 4) | nib[j + 1] for j in range(0, len(nib), 2)]

    r8 = ["  {" + ",".join(f"{b:3d}" for b in pack(f["nib"])) + f"}}, // {f['name']}"
          for f in b8]
    r16 = ["  {" + ",".join(str(b) for b in pack(f["nib"])) + f"}}, // {f['name']}"
           for f in b16]
    OUT_H.write_text(
        "#pragma once\n"
        "// GENERATED by spritegen.py — do not edit. 4bpp PAL index, high nibble =\n"
        "// left pixel, nibble 0 = transparent. Ids < SPR16_BASE are 8x8 (drawn 2x);\n"
        "// ids >= SPR16_BASE are native 16x16 (drawn 1x).\n"
        f"enum : uint16_t {{ {', '.join(enum)}, SPR_COUNT={len(order)} }};\n"
        f"static const uint16_t SPR16_BASE = {len(b8)};\n"
        f"static const uint8_t SPR_PX[{len(b8)}][32] = {{\n" + "\n".join(r8) + "\n};\n"
        f"static const uint8_t SPR16_PX[{len(b16)}][128] = {{\n" + "\n".join(r16) + "\n};\n")
    print(f"wrote {OUT_H}: {len(b8)} 8x8 + {len(b16)} 16x16 = {len(order)} sprites, "
          f"{len(b8)*32 + len(b16)*128} bytes")

    cat_lines = ["<!-- SPRITES:BEGIN generated by spritegen.py -->",
                 "## Sprite catalog (engine-baked, all drawn 16x16 on screen)"]
    for grp, entries in CATALOG.items():
        cat_lines.append(f"- {grp}: " + " · ".join(f"`SPR_{e[-2]}` {e[-1]}" for e in entries))
    cat_lines.append("<!-- SPRITES:END -->")
    cat = "\n".join(cat_lines)
    txt = PROMPT.read_text()
    marked = re.sub(r"<!-- SPRITES:BEGIN.*?SPRITES:END -->", cat, txt, flags=re.S)
    if marked == txt:
        marked = txt.rstrip() + "\n\n" + cat + "\n"
    PROMPT.write_text(marked)
    print(f"updated {PROMPT} catalog block ({len(cat)} chars)")

    if args.preview:
        from PIL import ImageDraw
        for tag, bank, size in (("8", b8, 8), ("16", b16, 16)):
            s = 96 // size
            cols = 14
            rows = (len(bank) + cols - 1) // cols
            im = Image.new("RGB", (cols * (size * s + 12), rows * (size * s + 26) + 4), (40, 40, 50))
            d = ImageDraw.Draw(im)
            for i, f in enumerate(bank):
                ox, oy = (i % cols) * (size * s + 12), (i // cols) * (size * s + 26) + 4
                for j, n in enumerate(f["nib"]):
                    c = (25, 25, 32) if n == TRANSP else PICO[n]
                    x, y = ox + (j % size) * s, oy + (j // size) * s
                    d.rectangle([x, y, x + s - 1, y + s - 1], fill=c)
                d.text((ox, oy + size * s + 2), f["name"][:11], fill=(255, 255, 0))
            im.save(f"{args.preview}_{tag}.png")
            print(f"wrote {args.preview}_{tag}.png")


if __name__ == "__main__":
    main()
