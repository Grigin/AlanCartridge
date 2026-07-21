import base64
import glob
import json
import os
import subprocess
import time
from pathlib import Path

import serial

from config import BAUD, FQBN, LIB, PORT_HINT, SKETCH
from music import score as music_score

SCREEN = LIB / ".screen"        # latest raw RGB565 frame (160*80*2 = 25600 B)
MIRROR_FLAG = LIB / ".mirror"   # GUI touches this while someone is watching
PORT_HB = LIB / ".port"         # heartbeat: a wait_for owns the serial port


def fresh(p, secs):
    try:
        return time.time() - p.stat().st_mtime < secs
    except OSError:
        return False


def store_frame(b64):
    """@F payload → library/.screen (atomic), silently dropping bad frames."""
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        return
    if len(raw) != 25600:
        return
    tmp = SCREEN.with_suffix(".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, SCREEN)

def port():
    if Path(PORT_HINT).exists():
        return PORT_HINT
    found = sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*")
                   + glob.glob("/dev/ttyUSB*"))
    return found[0] if found else PORT_HINT


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("arduino-cli not on PATH — see README setup")


def compile_sketch(out=None):
    args = ["arduino-cli", "compile", "--fqbn", FQBN]
    if out:
        args += ["--output-dir", str(out)]     # export bins for later flashing
    p = _run(args + [str(SKETCH)])
    out_ = p.stdout + p.stderr
    if p.returncode == 0:
        return True, out_
    keep = [l for l in out_.splitlines() if "error" in l.lower() or "game.ino" in l]
    return False, "\n".join(keep) or out_[-3000:]


def claim(secs=90):
    """Reserve the serial port for a foreground op (flash): a future-dated
    heartbeat keeps gui.py's console_pump off the wire while esptool talks.
    claim(0) hands the port back (the pump's freshness window is the grace)."""
    try:
        PORT_HB.touch()
        t = time.time() + secs
        os.utime(PORT_HB, (t, t))
    except OSError:
        pass


def upload(retries=3, input_dir=None):
    for attempt in range(retries):
        claim()                          # esptool must own the port alone
        args = ["arduino-cli", "upload", "-p", port(), "--fqbn", FQBN]
        if input_dir:
            args += ["--input-dir", str(input_dir)]   # flash prebuilt bins
        p = _run(args + [str(SKETCH)])
        if p.returncode == 0:
            claim(0)
            return True
        err = next((l.strip() for l in (p.stdout + p.stderr).splitlines()
                    if "error" in l.lower() or "failed" in l.lower()), "")
        print(f"  · flash attempt {attempt + 1} failed — "
              f"{err[:90] or 'port busy/re-enumerating?'} — retrying")
        time.sleep(2)
    claim(0)
    print(p.stdout + p.stderr)
    return False


def bless(timeout=10):
    """After a flash (or replug) the console boots into the blank gate —
    greet it so the title card appears without waiting for a watcher."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with serial.Serial(port(), BAUD, timeout=1) as s:
                while time.time() < end:
                    line = s.readline().decode(errors="ignore")
                    if '"blank"' in line or '"boot"' in line:
                        s.write(b"bless\n")
                        return True
        except serial.SerialException:
            time.sleep(1.5)          # port still re-enumerating after flash
    return False


def state(timeout=3):
    """Ping the console and return its current screen ("title"|"brief"|"play"|
    "over"|"blank"), or None if it can't tell (old firmware, port hiccup)."""
    try:
        with serial.Serial(port(), BAUD, timeout=1) as s:
            s.reset_input_buffer()
            s.write(b"ping\n")
            end = time.time() + timeout
            while time.time() < end:
                line = s.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("ev") == "pong":
                    return ev.get("shell")
    except serial.SerialException:
        pass
    return None


def wait_for(ev_name, mirror=False, cart=None, on_blank="bless"):
    """Block until the console emits {"ev": ev_name}. Survives port blinks.
    Returns with the port closed so the caller can flash. With mirror=True the
    same connection pumps framebuffer grabs while library/.mirror is fresh.
    `cart` is the flashed cartridge dir: its theme stops on game-over and
    restarts when the player (re)enters play. Heartbeats library/.port so
    gui.py's idle pump stays off the wire meanwhile.

    on_blank="bless" revives an empty console and keeps waiting (single-cart
    linger). "return" hands a blank back to the caller instead — a blank after
    any sign of life means the console REBOOTED out of a live game (cartridge
    crash, replug), which the buffered loop must treat as game-over or a
    crashing cart deadlocks it. A blank before any other event is always
    blessed: that's a boot announce whose bless() got missed, not a death."""
    last_req = last_hb = 0.0
    alive = False                       # saw any non-blank event on this wait
    while True:
        try:
            with serial.Serial(port(), BAUD, timeout=1) as s:
                while True:
                    if time.time() - last_hb > 2:
                        try:
                            PORT_HB.touch()
                        except OSError:
                            pass
                        last_hb = time.time()
                    if (mirror and time.time() - last_req > 0.6
                            and fresh(MIRROR_FLAG, 3)):
                        s.write(b"frame\n")
                        last_req = time.time()
                    line = s.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    if line.startswith("@F "):
                        store_frame(line[3:])
                        continue
                    try:                    # raw events stay out of the log
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("ev") == "blank":
                        if on_blank == "return" and alive:
                            music_score.on_console_event(ev, cart)  # silence it
                            return ev
                        s.write(b"bless\n")   # console booted empty — revive
                        continue
                    alive = True
                    music_score.on_console_event(ev, cart)
                    if ev.get("ev") == ev_name:
                        return ev
        except serial.SerialException:
            time.sleep(2)
            if state() == ev_name:      # the event fired into the dead port
                ev = {"ev": ev_name}    # (blink/replug mid-transition) — the
                music_score.on_console_event(ev, cart)   # shell still shows it
                return ev
