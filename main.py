import argparse
import atexit
import json
import os
import queue
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

import device
import game_factory
import ontology
from config import GAME_FILE, LIB, MODEL
from music import score as music_score


BUF_TARGET = 10                      # forged-ahead games kept ready to flash
QUEUE_FILE = LIB / "_queue.json"     # banked-but-unplayed dirs, oldest first
BUILD_TMP = LIB / ".build"           # arduino-cli --output-dir scratch
COORD_KEYS = ("title", "genre", "objective", "genre_objective", "twist",
              "setting", "pace", "wild_kind")   # meta coords = anti-repeat food


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
    coords = {k: des.get(k) for k in COORD_KEYS}
    (d / "meta.json").write_text(json.dumps(
        {**coords, "theme": theme, "seconds": round(seconds), "model": MODEL,
         "ts": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1))
    return d

def compose_theme_start(des, hist):
    """Kick the theme off in a thread — the LLM score and the mid/pt3/wav
    bake need nothing from the build, so they run under implement+compile.
    Returns a handle for compose_theme_finish once the cartridge dir exists."""
    out = {}

    def work():
        try:
            recent = [m["music"] for m in hist[-3:] if m.get("music")]
            sc = game_factory.compose(des, recent)
            tmp = Path(tempfile.mkdtemp(prefix=".theme_", dir=LIB))
            out["tmp"] = tmp
            out["stats"] = music_score.make_theme(tmp, sc, des["title"])
            out["score"] = sc               # success marker — set last
        except Exception as e:
            out["err"] = str(e)
    print("◆ composing theme (in parallel) ...")
    t = threading.Thread(target=work, daemon=True)
    t.start()
    return t, out


def compose_theme_finish(d, des, handle):
    """Adopt the baked theme into the cartridge dir and pre-load the .pt3
    onto the chip box — playing waits for the flash. Never raises; a failed theme
    ships the game silent."""
    t, out = handle
    t.join(timeout=120)                     # usually long done by compile end
    if t.is_alive() or "score" not in out:
        if not t.is_alive() and out.get("tmp"):
            shutil.rmtree(out["tmp"], ignore_errors=True)
        print("  ♪ theme failed — shipping silent "
              f"({out.get('err', 'still composing')[:90]})")
        return
    try:
        for f in ("theme.json", "theme.mid", "theme.pt3", "theme.wav"):
            shutil.move(str(out["tmp"] / f), str(d / f))
        shutil.rmtree(out["tmp"], ignore_errors=True)
        meta = json.loads((d / "meta.json").read_text())
        meta["music"] = {"tempo": out["score"].get("tempo"),
                         "flavor": out["score"].get("flavor") or {}}
        (d / "meta.json").write_text(json.dumps(meta, indent=1))
        if os.environ.get("FORGE_GUI"):    # structured — the GUI shows a ▶ card
            print("@music " + json.dumps({"dir": d.name, "title": des["title"],
                                          "tempo": out["score"].get("tempo")}))
        else:
            print(f"  ♪ {out['stats']}")
        music_score.chip_save(f"{d.name}.pt3",
                                 (d / "theme.pt3").read_bytes())
    except Exception as e:
        print(f"  ♪ theme failed — shipping silent ({str(e)[:90]})")


def llm_stage(theme, hist):
    """Everything up to raw game code — API calls only, never touches
    forge_sketch/ or the compiler, so it can overlap a build_stage.
    Returns (des, code, music-handle) or None when the skin is unusable."""
    sg = ss = None
    if theme:
        sg, ss = game_factory.theme_steer(
            theme,
            [g for g in ontology.GENRES if g not in ontology.DISABLED_GENRES],
            list(ontology.SETTINGS))
        print(f"◆ theme steers → genre: {sg or '(roll)'} · setting: {ss or '(roll)'}")
    coords = ontology.roll(hist, force_genre=sg, force_setting=ss)
    if os.environ.get("FORGE_GUI"):    # structured roll — the web GUI draws dice
        print("@roll " + json.dumps({k: coords.get(k) for k in
              ("genre", "objective", "verb", "goal", "twist", "pace",
               "setting", "avatar", "wild_kind")}))
    else:
        print(f"◆ rolled {coords['genre_objective']} · {coords['verb']} {coords['goal']}"
              f" · twist {coords['twist']} · {coords['pace']} · {coords['setting']}"
              + (f" · WILD:{coords['wild_kind']}" if coords.get("wild_kind") else ""))
    print(f"◆ skinning{f' for theme: {theme}' if theme else ''} ...")
    des, derrs = None, []
    for attempt in (1, 2):
        try:
            cand = game_factory.skin(coords, theme, hist,
                                     fix="; ".join(derrs) or None)
            cerrs = game_factory.design_check(cand)
        except ValueError as e:
            cand, cerrs = None, [str(e)]
        if cand is not None:
            des = cand                      # keep the latest parseable design
        derrs = cerrs
        if not derrs:
            break
        if attempt == 1:
            print("  · reskin: " + "; ".join(derrs)[:100])
    if des is None:
        print("  ✗ skin unusable twice — skipping this forge")
        return None
    if derrs:
        print("  ! design imperfect, forging anyway: " + "; ".join(derrs)[:100])
    if os.environ.get("FORGE_GUI"):    # structured skin — the GUI draws the avatar
        print("@skin " + json.dumps({"title": des["title"],
                                     "blurb": des.get("blurb", ""),
                                     "avatar": des.get("avatar")}))
    else:
        print(f"  → {des['title']} — {des.get('blurb', '')}")
    mus = compose_theme_start(des, hist)      # rides under implement+compile
    print("◆ implementing ...")
    return des, game_factory.implement(des), mus


def build_stage(des, code, mus, theme, t0, flash=False):
    """Static check -> compile -> repair (≤3), then bank the cartridge and
    adopt its theme. Owns forge_sketch/ and BUILD_TMP — never run two at
    once (the pipeline's single build worker is that guarantee)."""
    print(f"◆ building {des['title']} ...")
    mapblk = game_factory.map_code(des)       # generated once, repair-immune
    for attempt in range(1, 4):
        errs = game_factory.static_check(code + mapblk)
        if not errs:
            GAME_FILE.write_text(code + mapblk)
            ok, log = device.compile_sketch(out=BUILD_TMP)
            if ok:
                break
            errs = [log]
        if attempt == 3:
            dump = LIB / f"_failed_{time.strftime('%H%M%S')}"
            dump.mkdir(parents=True, exist_ok=True)
            (dump / "game.ino").write_text(code + mapblk)
            (dump / "errors.txt").write_text("\n".join(errs))
            print(f"  ✗ forge failed — autopsy in {dump}"
                  + ("; previous game still on device" if flash else "; batch continues"))
            mt, mout = mus               # reap the game's music bake too
            if not mt.is_alive() and mout.get("tmp"):
                shutil.rmtree(mout["tmp"], ignore_errors=True)
            return None
        print(f"  ✗ attempt {attempt} rejected:")
        for e in "\n".join(errs).splitlines()[:4]:
            print(f"      {e[:110]}")
        code = game_factory.repair(code, "\n".join(errs), des)
    d = save(des, code + mapblk, theme, time.time() - t0)
    bd = d / "build"                 # keep the bins — loop flashes them directly
    bd.mkdir(exist_ok=True)
    for f in BUILD_TMP.glob("*.bin"):
        if "merged" not in f.name:
            shutil.copy2(f, bd / f.name)
    print(f"  ✓ compiled in {time.time() - t0:.0f}s → {d.name}")
    compose_theme_finish(d, des, mus)
    return d


def forge_one(theme=None, flash=True):
    t0 = time.time()
    r = llm_stage(theme, history())
    if r is None:
        return None
    d = build_stage(*r, theme, t0, flash)
    if d and flash:
        print("◆ flashing ...")
        if device.upload():
            print(f"  ✓ LIVE in {time.time() - t0:.0f}s total")
            device.bless()               # wake the console out of its boot gate
            music_score.play_for(d)
    return d


def pipeline(room, on_saved, theme=None, on_spent=None):
    """Two-stage producer: an LLM worker (roll/skin/implement — API only)
    feeds a single build worker (compile/repair/save — owns the sketch dir),
    so game N+1 is authored while game N compiles. `room(in_flight)` gates
    admission, `on_saved(d)` banks finished cartridges, `on_spent()` fires
    once per admitted attempt when it fully leaves the system (banked,
    autopsied, or skinless). Workers are daemons; both survive exceptions."""
    pending = []          # coords past the LLM stage, not yet saved/failed
    plock = threading.Lock()
    handq = queue.Queue(maxsize=1)   # ≤1 authored game waits on the builder

    def spend():
        if on_spent:
            with plock:
                on_spent()

    def llm_worker():
        while True:
            try:
                with plock:
                    k = len(pending)
                if not room(k):
                    time.sleep(3)
                    continue
                t0 = time.time()
                # a just-saved game may briefly sit in both history() and
                # pending — the duplicate only strengthens anti-repeat
                with plock:
                    eff = history() + list(pending)
                r = llm_stage(theme, eff)
                if r is None:
                    spend()
                    time.sleep(15)   # unusable skin — breathe, then retry
                    continue
                pend = {k2: r[0].get(k2) for k2 in COORD_KEYS}
                with plock:
                    pending.append(pend)
                handq.put((r, pend, t0))
            except Exception as e:
                print(f"  ✗ producer hiccup (author): {str(e)[:120]}")
                time.sleep(15)

    def build_worker():
        while True:
            r, pend, t0 = handq.get()
            try:
                d = build_stage(*r, theme, t0)
            except Exception as e:
                print(f"  ✗ producer hiccup (build): {str(e)[:120]}")
                d = None
            with plock:
                if pend in pending:
                    pending.remove(pend)
            if d:
                on_saved(d)
            spend()
    threading.Thread(target=llm_worker, daemon=True).start()
    threading.Thread(target=build_worker, daemon=True).start()


def load_queue():
    try:
        q = json.loads(QUEUE_FILE.read_text())
        return [d for d in q if (LIB / d / "build").is_dir()]
    except Exception:
        return []


def save_queue(q):
    QUEUE_FILE.write_text(json.dumps(q))


def flash_built(d):
    print(f"◆ flashing {d.name} ...")
    if device.upload(input_dir=d / "build"):
        print("  ✓ LIVE")
        device.bless()                   # wake the console out of its boot gate
        music_score.play_for(d)
        return True
    print("  ✗ flash failed — previous game still on device")
    return False


def play_loop(theme):
    q = load_queue()
    qlock = threading.Lock()

    def farewell():                      # wipe the buffer on shutdown: keep one
        with qlock:                      # warm opener, the rest re-forge fresh
            if len(q) > 1:
                kept, dropped = q[0], len(q) - 1
                del q[1:]
                save_queue(q)
                print(f"\n◇ buffer wiped — kept {kept} warm, "
                      f"{dropped} slot{'s' if dropped > 1 else ''} re-forge next boot")
    atexit.register(farewell)
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))   # so atexit runs

    cur = None                           # cartridge live on the device
    if q:                                # unplayed games survive restarts
        d = q.pop(0)
        save_queue(q)
        print(f"◆ resuming buffer ({len(q) + 1} banked)")
        if flash_built(LIB / d):
            cur = LIB / d
    else:
        cur = forge_one(theme)           # forge & flash the opening cartridge

    def room(in_flight):                 # admit while bank + in-flight < 10
        with qlock:
            n = len(q)
        if n + in_flight >= BUF_TARGET:
            return False
        print(f"◆ buffer {n}/{BUF_TARGET} — forging ahead"
              + (f" ({in_flight} in flight)" if in_flight else ""))
        return True

    def banked(d):
        with qlock:
            q.append(d.name)
            save_queue(q)
    pipeline(room, banked)               # authors N+1 while N compiles

    while True:
        print("◆ watching console — next cartridge on game-over")
        ev = device.wait_for("over", mirror=True, cart=cur, on_blank="return")
        if ev.get("ev") == "blank":      # console rebooted out of the game —
            print("  ◇ cartridge died mid-run (console rebooted) — "
                  "inserting the next one")
        waited = False
        while True:
            with qlock:
                if q:
                    d = q.pop(0)
                    save_queue(q)
                    break
            if not waited:
                print("◆ buffer empty — the forge is mid-game, hold on")
                waited = True
            time.sleep(2)
        if waited:                       # player may have replayed meanwhile —
            sh = device.state()          # never yank a live run; title/over/
            while sh in ("play", "brief"):   # blank = idle, flash right away
                print("◆ replay in progress — flashing after this run")
                if cur:                      # its "play" fired while we were off
                    music_score.play_for(cur)     # the wire — restart the theme
                device.wait_for("over", mirror=True, cart=cur, on_blank="return")
                sh = "over"
        if flash_built(LIB / d):
            cur = LIB / d


def flash_lib(path):
    src = Path(path) / "game.ino"
    if not src.exists():
        sys.exit(f"no such cartridge: {path} — have: "
                 + " ".join(d.name for d in sorted(LIB.glob("[0-9]*"))))
    GAME_FILE.write_text(src.read_text())
    ok, log = device.compile_sketch()
    if not ok:
        sys.exit(log)
    if not device.upload():
        sys.exit(1)
    device.bless()
    music_score.play_for(Path(path))
    sys.exit(0)


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
    for p in LIB.glob(".theme_*"):       # bake dirs orphaned by a dead forge
        shutil.rmtree(p, ignore_errors=True)
    if a.list:
        catalogue()
    elif a.flash:
        flash_lib(a.flash)
    elif a.pregen:
        state = {"started": 0, "spent": 0}   # attempts, like the old for-loop

        def admit(in_flight):
            if state["started"] >= a.pregen:
                return False
            state["started"] += 1            # llm_worker only — no race
            return True
        pipeline(admit, lambda d: None, a.theme,
                 on_spent=lambda: state.update(spent=state["spent"] + 1))
        while state["spent"] < a.pregen:     # pipelined batch: block to drain
            time.sleep(1)
    elif a.loop:
        play_loop(a.theme)
    else:
        d = forge_one(a.theme)
        np = music_score.NOWPLAYING      # last successfully flashed cartridge
        if d and not os.environ.get("FORGE_GUI") and np.exists():
            print("◆ watching console — music follows the game (Ctrl-C exits)")
            try:
                while True:              # over silences, replay restarts
                    device.wait_for("over", mirror=True,
                                    cart=LIB / np.read_text().strip())
            except KeyboardInterrupt:
                pass
