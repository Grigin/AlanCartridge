import argparse
import json
import re
import sys
import time
from pathlib import Path

import device
import game_factory
import ontology
from config import GAME_FILE, LIB, MODEL


def history():
    """Coords dicts (oldest first) from meta.json — the anti-repeat memory."""
    out = []
    for m in sorted(LIB.glob("*/meta.json")):
        try:
            out.append(json.loads(m.read_text()))
        except Exception:
            pass
    return out


def next_slot():
    nums = [int(d.name[:3]) for d in LIB.iterdir()
            if d.is_dir() and d.name[:3].isdigit()]
    return max(nums, default=0) + 1

def slug(t):
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_") or "game"

def save(des, code, theme, seconds):
    d = LIB / f"{next_slot():03d}_{slug(des['title'])}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "game.ino").write_text(code)
    (d / "design.json").write_text(json.dumps(des, indent=1))
    coords = {k: des.get(k) for k in ("title", "genre", "objective",
                                      "genre_objective", "twist", "setting", "pace")}
    (d / "meta.json").write_text(json.dumps(
        {**coords, "theme": theme, "seconds": round(seconds), "model": MODEL,
         "ts": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1))
    return d

def forge_one(theme=None, flash=True):
    t0 = time.time()
    hist = history()
    coords = ontology.roll(hist)
    print(f"◆ rolled {coords['genre_objective']} · {coords['verb']} {coords['goal']}"
          f" · twist {coords['twist']} · {coords['pace']} · {coords['setting']}")
    print(f"◆ skinning{f' for theme: {theme}' if theme else ''} ...")
    des = game_factory.skin(coords, theme, hist)
    derrs = game_factory.design_check(des)
    if derrs:
        print("  · reskin: " + "; ".join(derrs)[:100])
        des = game_factory.skin(coords, theme, hist, fix="; ".join(derrs))
        derrs = game_factory.design_check(des)
        if derrs:
            print("  ! design imperfect, forging anyway: " + "; ".join(derrs)[:100])
    print(f"  → {des['title']} — {des.get('blurb', '')}")
    print("◆ implementing ...")
    code = game_factory.implement(des)
    ok = False
    for attempt in range(1, 4):
        errs = game_factory.static_check(code)
        if not errs:
            GAME_FILE.write_text(code)
            ok, log = device.compile_sketch()
            if ok:
                break
            errs = [log]
        if attempt == 3:
            dump = LIB / f"_failed_{time.strftime('%H%M%S')}"
            dump.mkdir(parents=True, exist_ok=True)
            (dump / "game.ino").write_text(code)
            (dump / "errors.txt").write_text("\n".join(errs))
            print(f"  ✗ forge failed — autopsy in {dump}; previous game still on device")
            return None
        print(f"  ✗ attempt {attempt} rejected:")
        for e in "\n".join(errs).splitlines()[:4]:
            print(f"      {e[:110]}")
        code = game_factory.repair(code, "\n".join(errs), des)
    d = save(des, code, theme, time.time() - t0)
    print(f"  ✓ compiled in {time.time() - t0:.0f}s → {d.name}")
    if flash:
        print("◆ flashing ...")
        if device.upload():
            print(f"  ✓ LIVE in {time.time() - t0:.0f}s total")
    return d


def play_loop(theme):
    forge_one(theme)
    while True:
        print("◆ watching console — forge triggers on game-over")
        device.wait_for("over")
        forge_one(None)


def flash_lib(path):
    src = Path(path) / "game.ino"
    if not src.exists():
        sys.exit(f"no such cartridge: {path} — have: "
                 + " ".join(d.name for d in sorted(LIB.glob("[0-9]*"))))
    GAME_FILE.write_text(src.read_text())
    ok, log = device.compile_sketch()
    if not ok:
        sys.exit(log)
    sys.exit(0 if device.upload() else 1)


def catalogue():
    for d in sorted(LIB.glob("[0-9]*")):
        meta = {}
        try:
            meta = json.loads((d / "meta.json").read_text())
        except Exception:
            pass
        print(f"{d.name:28s} {meta.get('genre_objective') or '?':18s} "
              f"{meta.get('twist') or '?':9s} {meta.get('setting') or '?':10s} "
              f"{meta.get('seconds', '?')}s  theme: {meta.get('theme') or '—'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--pregen", type=int, default=0)
    ap.add_argument("--flash", metavar="LIBDIR")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    LIB.mkdir(exist_ok=True)
    if a.list:
        catalogue()
    elif a.flash:
        flash_lib(a.flash)
    elif a.pregen:
        for _ in range(a.pregen):
            forge_one(a.theme, flash=False)
    elif a.loop:
        play_loop(a.theme)
    else:
        forge_one(a.theme)
