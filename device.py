import glob
import json
import subprocess
import time
from pathlib import Path

import serial

from config import BAUD, FQBN, PORT_HINT, SKETCH

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


def compile_sketch():
    p = _run(["arduino-cli", "compile", "--fqbn", FQBN, str(SKETCH)])
    out = p.stdout + p.stderr
    if p.returncode == 0:
        return True, out
    keep = [l for l in out.splitlines() if "error" in l.lower() or "game.ino" in l]
    return False, "\n".join(keep) or out[-3000:]


def upload(retries=3):
    for attempt in range(retries):
        p = _run(["arduino-cli", "upload", "-p", port(), "--fqbn", FQBN, str(SKETCH)])
        if p.returncode == 0:
            return True
        print(f"  · flash attempt {attempt + 1} failed — port re-enumerating? retrying")
        time.sleep(2)
    print(p.stdout + p.stderr)
    return False


def wait_for(ev_name):
    """Block until the console emits {"ev": ev_name}. Survives port blinks.
    Returns with the port closed so the caller can flash."""
    while True:
        try:
            with serial.Serial(port(), BAUD, timeout=1) as s:
                while True:
                    line = s.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    print("  console:", line)
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("ev") == ev_name:
                        return ev
        except serial.SerialException:
            time.sleep(2)
