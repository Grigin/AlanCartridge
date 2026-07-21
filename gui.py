import argparse
import atexit
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import serial

import device as dev
from config import LIB, MODEL, PORT_HINT, ROOT
from music import score as music_score

LOG = deque(maxlen=4000)
LOCK = threading.Lock()
S = {"proc": None, "label": "", "total": 0, "exit": None}


def busy():
    p = S["proc"]
    return p is not None and p.poll() is None


def push(line):
    with LOCK:
        LOG.append(line)
        S["total"] += 1


def pump(p):
    for line in p.stdout:
        push(line)
    S["exit"] = p.wait()
    push(f"— exit {S['exit']} —\n")


def launch(args, label):
    if busy():
        return False
    push(f"$ main.py {' '.join(args)}\n")
    # -u: piped stdout is block-buffered otherwise — the log must stream live
    S["proc"] = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "main.py"), *args],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "FORGE_GUI": "1"})
    S["label"], S["exit"] = label, None
    threading.Thread(target=pump, args=(S["proc"],), daemon=True).start()
    return True


def build_args(req):
    """Constrained request → argv; anything off-menu raises. Keeps a stray
    local page from POSTing arbitrary arguments into main.py."""
    cmd = req.get("cmd")
    theme = str(req.get("theme") or "").strip()[:100]
    t = ["--theme", theme] if theme else []
    if cmd == "forge":
        return t, "forge"
    if cmd == "loop":
        return ["--loop"] + t, "loop"
    if cmd == "pregen":
        n = int(req.get("n", 3))
        if not 1 <= n <= 20:
            raise ValueError("n out of range")
        return ["--pregen", str(n)] + t, f"pregen {n}"
    if cmd == "list":
        return ["--list"], "list"
    if cmd == "flash":
        d = req.get("dir", "")
        if not re.fullmatch(r"[0-9]{3}_[a-z0-9_]+", d) or not (LIB / d).is_dir():
            raise ValueError("bad cartridge dir")
        return ["--flash", f"library/{d}"], f"flash {d}"
    raise ValueError("unknown cmd")


_libcache = (None, [])


def library():
    global _libcache
    dirs = sorted(d for d in LIB.glob("[0-9]*") if d.is_dir())
    metas = [d / "meta.json" for d in dirs]
    wavs = [d / "theme.wav" for d in dirs]
    try:
        key = (LIB.stat().st_mtime_ns, len(dirs),
               sum(1 for m in metas if m.exists()),
               sum(1 for w in wavs if w.exists()))
    except OSError:
        key = None
    if key is not None and _libcache[0] == key:
        return _libcache[1]
    out = []
    for m, w in zip(metas, wavs):
        try:
            meta = json.loads(m.read_text())
        except Exception:
            meta = {}
        out.append({"dir": m.parent.name,
                    "title": meta.get("title") or m.parent.name[4:],
                    "genre": meta.get("genre_objective") or "?",
                    "twist": meta.get("twist") or "?",
                    "setting": meta.get("setting") or "?",
                    "theme": meta.get("theme") or "",
                    "wav": w.exists()})
    _libcache = (key, out)
    return out


PICO = ["#000000", "#1d2b53", "#7e2553", "#008751", "#ab5236", "#5f574f",
        "#c2c3c7", "#fff1e8", "#ff004d", "#ffa300", "#ffec27", "#00e436",
        "#29adff", "#83769c", "#ff77a8", "#ffccaa"]

_sprcache = None


def sprites():
    """Parse forge_sketch/sprites.h once: ids, alt table, 4bpp pixel rows."""
    global _sprcache
    if _sprcache is None:
        txt = (ROOT / "forge_sketch" / "sprites.h").read_text()
        ids = {m.group(1): int(m.group(2))
               for m in re.finditer(r"(SPR_\w+)=(\d+)", txt)}
        base = int(re.search(r"SPR16_BASE = (\d+)", txt).group(1))
        alt = [int(x) for x in re.search(
            r"SPR_ALT\[\d+\] = \{([^}]*)\}", txt).group(1).split(",")]

        def rows(name):
            block = txt[txt.index(name):]
            block = block[:block.index("};")]
            return [[int(b) for b in r.split(",")]
                    for r in re.findall(r"\{([^{}]*)\}", block)]
        _sprcache = (ids, base, alt, rows("SPR_PX"), rows("SPR16_PX"))
    return _sprcache


def spr_frames(name):
    ids, base, alt, px8, px16 = sprites()
    if name not in ids or ids[name] >= len(alt):
        return None

    def decode(i):                       # high nibble = left pixel, 0 = transparent
        data, w = (px8[i], 8) if i < base else (px16[i - base], 16)
        return [[data[(y * w + x) // 2] >> 4 if x % 2 == 0
                 else data[(y * w + x) // 2] & 15
                 for x in range(w)] for y in range(w)]
    i = ids[name]
    frames = [decode(i)]
    if alt[i] != i:                      # walk cycle pair from SPR_ALT
        frames.append(decode(alt[i]))
    return {"name": name, "w": 8 if i < base else 16,
            "pal": PICO, "frames": frames}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _local(self):
        return (self.headers.get("Host") or "").split(":")[0] in (
            "127.0.0.1", "localhost")

    def do_GET(self):
        if not self._local():
            return self._json({"err": "forbidden"}, 403)
        if self.path.split("?")[0] in ("/", "/dev"):
            try:
                b = (ROOT / "gui.html").read_bytes()
            except OSError:
                return self._json({"err": "gui.html missing"}, 500)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path == "/dice.mp3":
            try:
                b = (ROOT / "assets" / "audio" / "dice.mp3").read_bytes()
            except OSError:
                return self._json({"err": "dice.mp3 missing"}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path == "/api/screen":
            try:
                dev.MIRROR_FLAG.touch()      # "someone is watching" signal
            except OSError:
                pass
            try:
                if dev.fresh(dev.SCREEN, 2.5):
                    b = dev.SCREEN.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(b)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(b)
                    return
            except OSError:
                pass
            self.send_response(204)
            self.end_headers()
            return
        if self.path.startswith("/api/wav/"):
            name = self.path.split("/")[-1].split("?")[0]
            if not re.fullmatch(r"[0-9]{3}_[a-z0-9_]+", name or ""):
                return self._json({"err": "bad name"}, 400)
            try:
                b = (LIB / name / "theme.wav").read_bytes()
            except OSError:
                return self._json({"err": "no theme"}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path.startswith("/api/sprite/"):
            name = self.path.split("/")[-1].split("?")[0]
            if not re.fullmatch(r"SPR_\w{1,40}", name or ""):
                return self._json({"err": "bad name"}, 400)
            try:
                out = spr_frames(name)
            except Exception as e:
                return self._json({"err": f"sprites.h parse: {e}"}, 500)
            if out is None:
                return self._json({"err": "unknown sprite"}, 404)
            return self._json(out)
        if self.path.startswith("/api/state"):
            qs = parse_qs(urlparse(self.path).query)
            since = int(qs.get("since", ["0"])[0])
            with LOCK:
                base = S["total"] - len(LOG)
                lines = (list(LOG)[max(0, since - base):]
                         if since < S["total"] else [])
                total = S["total"]
            return self._json({"busy": busy(), "label": S["label"],
                               "exit": S["exit"], "total": total,
                               "lines": lines, "library": library(),
                               "port": PORT_HINT, "model": MODEL})
        self._json({"err": "not found"}, 404)

    def do_POST(self):
        if not self._local():
            return self._json({"err": "forbidden"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json({"err": "bad json"}, 400)
        if self.path == "/api/run":
            try:
                args, label = build_args(req)
            except (ValueError, TypeError) as e:
                return self._json({"err": str(e) or "bad request"}, 400)
            if not launch(args, label):
                return self._json({"err": "busy"}, 409)
            S["tetris"] = False              # a run's theme takes over the chip
            return self._json({"ok": True})
        if self.path == "/api/tetris":          # /dev toy: Korobeiniki on the chip
            if S.get("tetris"):                  # second press stops it
                music_score.chip_stop()
                S["tetris"] = False
                return self._json({"ok": True, "playing": False})
            pt3 = ROOT / "music" / "tetris.pt3"
            if not pt3.exists():
                return self._json({"err": "tetris.pt3 missing"}, 404)
            ok = music_score.chip_save("tetris.pt3", pt3.read_bytes(), play=True)
            S["tetris"] = bool(ok)
            return self._json({"ok": bool(ok), "playing": bool(ok)})
        if self.path == "/api/stop":
            p = S["proc"]
            if p and p.poll() is None:
                push("— stopping (a stop mid-upload leaves the device needing"
                     " a reflash) —\n")
                p.terminate()
                threading.Timer(
                    3, lambda: p.poll() is None and p.kill()).start()
            return self._json({"ok": True})
        self._json({"err": "not found"}, 404)


def console_pump():
    """Own the serial port while no child does (a wait_for heartbeats
    library/.port; runs launched here flip busy()): pump mirror frames when
    the page watches, and run the music lifecycle — game-over silences the
    box, a replay restarts the flashed cartridge's theme. Covers the
    idle/just-forged case; loop children handle all of this themselves."""
    s = None
    last_req = 0.0

    def drop():
        nonlocal s
        try:
            if s:
                s.close()
        except Exception:
            pass
        s = None
    while True:
        want = (dev.fresh(dev.MIRROR_FLAG, 3)
                or music_score.NOWPLAYING.exists())
        if busy() or dev.fresh(dev.PORT_HB, 5) or not want:
            drop()
            time.sleep(1)
            continue
        try:
            if s is None:
                s = serial.Serial(dev.port(), 115200, timeout=1)
                s.reset_input_buffer()
            if dev.fresh(dev.MIRROR_FLAG, 3) and time.time() - last_req > 0.6:
                s.write(b"frame\n")
                last_req = time.time()
            line = s.readline().decode(errors="ignore").strip()
            if not line:
                continue
            if line.startswith("@F "):
                dev.store_frame(line[3:])
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            # a blank console stays blank here — blessing is reserved for
            # forge/loop/flash actions, so the cartridge feels evaporated
            try:
                cart = LIB / music_score.NOWPLAYING.read_text().strip()
            except OSError:
                cart = None
            music_score.on_console_event(ev, cart)
        except Exception:
            drop()
            time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8734)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    url = f"http://127.0.0.1:{a.port}"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError:
        print(f"port {a.port} busy — GUI already running? opening {url}")
        webbrowser.open(url)
        return
    atexit.register(lambda: busy() and S["proc"].terminate())
    threading.Thread(target=console_pump, daemon=True).start()
    print(f"◆ INFINITE CARTRIDGE GUI — {url}  (Ctrl-C quits and stops any"
          " running forge)")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
