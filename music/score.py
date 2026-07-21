import contextlib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import mido

from config import LIB, ZX_SPECTRUM_CHIP

from .midi2pt3 import midi_to_pt3   # importing this vendors spectrumizer too

NOWPLAYING = LIB / ".nowplaying"    # dir name of the last flashed themed cart

LO, HI = 33, 96                     # A1..C7 — the AY's comfortable register
MIN_16, MAX_16 = 32, 256            # loop length: 8..64 beats in sixteenths
MAX_EVENTS = 400
DRUMS = {"K": (36, 110), "S": (38, 100), "H": (42, 70), "O": (46, 85)}
FLAVOR = {"style": ("faithful", "chiptune"),
          "bass": ("normal", "envelope", "envelope-tone")}
TPB = 480                           # MIDI ticks per beat; a sixteenth is TPB/4

_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitch(v):
    """"F#3" / "Bb4" / plain int -> MIDI note number. ValueError on nonsense."""
    if isinstance(v, int):
        return v
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", str(v).strip())
    if not m:
        raise ValueError(f"bad pitch {v!r}")
    n = _PC[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return n + 12 * (int(m.group(3)) + 1)


def check(score):
    """Non-LLM gate on a composed score — same spirit as design_check."""
    if not isinstance(score, dict):
        return ["score must be a JSON object"]
    errs = []
    t = score.get("tempo")
    if not (isinstance(t, (int, float)) and 70 <= t <= 200):
        errs.append("tempo must be 70..200 bpm")
    fl = score.get("flavor") or {}
    for k, allowed in FLAVOR.items():
        if k in fl and fl[k] not in allowed:
            errs.append(f"flavor.{k} must be one of {allowed}")
    for k in ("arps", "echo", "vibrato"):
        if k in fl and not isinstance(fl[k], bool):
            errs.append(f"flavor.{k} must be true/false")
    events, end, reg = 0, 0, {}
    for tr in ("lead", "bass", "harmony"):
        notes = score.get(tr) or []
        if tr != "harmony" and not notes:
            errs.append(f"required track {tr} is empty")
        ps = []
        for n in notes:
            if not (isinstance(n, list) and len(n) in (3, 4)):
                errs.append(f"{tr}: notes are [pitch,start,dur] or "
                            "[pitch,start,dur,vel]")
                break
            try:
                p = pitch(n[0])
            except ValueError:
                errs.append(f"{tr}: bad pitch {n[0]!r}")
                break
            if not LO <= p <= HI:
                errs.append(f"{tr}: pitch {n[0]} outside A1..C7")
                break
            if not (isinstance(n[1], int) and n[1] >= 0
                    and isinstance(n[2], int) and n[2] >= 1):
                errs.append(f"{tr}: start/dur must be sixteenth ints "
                            "(start >= 0, dur >= 1)")
                break
            if len(n) == 4 and not (isinstance(n[3], int) and 1 <= n[3] <= 127):
                errs.append(f"{tr}: velocity must be 1..127")
                break
            ps.append(p)
            end = max(end, n[1] + n[2])
        events += len(notes)
        if ps:
            reg[tr] = sum(ps) / len(ps)
    for d in score.get("drums") or []:
        if not (isinstance(d, list) and len(d) == 2 and d[0] in DRUMS
                and isinstance(d[1], int) and d[1] >= 0):
            errs.append('drums: entries are ["K"|"S"|"H"|"O", start16]')
            break
        end = max(end, d[1] + 1)
    events += len(score.get("drums") or [])
    if events > MAX_EVENTS:
        errs.append(f"{events} events — keep under {MAX_EVENTS}")
    if not errs and not MIN_16 <= end <= MAX_16:
        errs.append(f"piece spans {end} sixteenths — keep {MIN_16}..{MAX_16} "
                    "(8..64 beats)")
    if reg.get("bass", -1) >= reg.get("lead", 999):
        errs.append("bass must sit below the lead — the arranger assigns "
                    "voices by register")
    return errs


def _track(ev):
    """(abs_tick, order, msg) list -> delta-time MidiTrack (offs before ons)."""
    tr = mido.MidiTrack()
    now = 0
    for tick, _, msg in sorted(ev, key=lambda e: (e[0], e[1])):
        msg.time = tick - now
        tr.append(msg)
        now = tick
    return tr


def build_midi(score, path):
    """Score JSON -> standard MIDI file spectrumizer's load_midi understands:
    lead/bass/harmony on channels 0/1/2, drums as GM hits on channel 10."""
    t16 = TPB // 4
    mid = mido.MidiFile(ticks_per_beat=TPB)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage(
        "set_tempo", tempo=mido.bpm2tempo(float(score["tempo"])), time=0))
    mid.tracks.append(meta)
    for name, ch in (("lead", 0), ("bass", 1), ("harmony", 2)):
        notes = score.get(name) or []
        if not notes:
            continue
        ev = []
        for n in notes:
            p, v = pitch(n[0]), n[3] if len(n) == 4 else 96
            ev.append((n[1] * t16, 1, mido.Message(
                "note_on", channel=ch, note=p, velocity=v, time=0)))
            ev.append(((n[1] + n[2]) * t16, 0, mido.Message(
                "note_off", channel=ch, note=p, velocity=0, time=0)))
        mid.tracks.append(_track(ev))
    drums = score.get("drums") or []
    if drums:
        ev = []
        for sym, s in drums:
            p, v = DRUMS[sym]
            ev.append((s * t16, 1, mido.Message(
                "note_on", channel=9, note=p, velocity=v, time=0)))
            ev.append((s * t16 + t16, 0, mido.Message(
                "note_off", channel=9, note=p, velocity=0, time=0)))
        mid.tracks.append(_track(ev))
    mid.save(str(path))


def render_wav(pt3, wav, cap=30.0):
    """Audition snippet through spectrumizer's software AY. Returns seconds."""
    from spectrumizer import audio
    from spectrumizer.pt3.player import parse_module
    module = parse_module(Path(pt3).read_bytes())
    nat = audio.duration_seconds(module)
    pcm, ch = audio.render_pcm(module, stereo="abc",
                               max_seconds=cap if nat > cap else None)
    audio.write_wav(str(wav), pcm, channels=ch)
    return len(pcm) / ch / 44100


def make_theme(d, score, title):
    """Bake a checked score into d/theme.{json,mid,pt3,wav}; returns a stats
    line for the log."""
    d = Path(d)
    (d / "theme.json").write_text(json.dumps(score))
    build_midi(score, d / "theme.mid")
    fl = score.get("flavor") or {}
    opts = {k: True for k in ("arps", "echo", "vibrato") if fl.get(k) is True}
    if fl.get("bass") in ("envelope", "envelope-tone"):
        opts["bass"] = fl["bass"]
    with contextlib.redirect_stdout(io.StringIO()):   # its stats line is noise
        midi_to_pt3(d / "theme.mid", d / "theme.pt3",
                    style=fl.get("style") or "chiptune",
                    name=str(title).upper()[:32], author="INFINITE CARTRIDGE",
                    **opts)
    secs = render_wav(d / "theme.pt3", d / "theme.wav")
    return (f"{float(score['tempo']):.0f} bpm · {fl.get('style') or 'chiptune'}"
            f" · {secs:.0f}s snippet")


def _post(path, data=b"", quiet=False):
    if not ZX_SPECTRUM_CHIP:
        return False
    try:
        req = urllib.request.Request(
            ZX_SPECTRUM_CHIP.rstrip("/") + path, data=data, method="POST",
            headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=3) as r:
            r.read()
        return True
    except Exception as e:
        if not quiet:
            print(f"  ♪ ZX Spectrum Chip: {e} — music skipped")
        return False


def chip_save(name, data, play=False):
    return _post("/songs?name=" + urllib.parse.quote(name)
                 + ("&play=1" if play else ""), data)


def chip_play(name):
    return _post("/play?song=" + urllib.parse.quote(name), quiet=True)


def chip_stop():
    return _post("/stop", quiet=True)


def play_for(d):
    """Start a cartridge's theme: a tiny /play of the pre-loaded track, with
    a save+play fallback when the box missed the upload. Theme-less legacy
    cartridges stop the music — silence beats the previous game's tune.
    Called on flash-complete and again on every (re)entry into play."""
    d = Path(d)
    pt3 = d / "theme.pt3"
    if not pt3.exists():
        chip_stop()
        NOWPLAYING.unlink(missing_ok=True)
        return
    try:
        NOWPLAYING.write_text(d.name)   # what's live, even if the box is down
    except OSError:
        pass
    if (chip_play(f"{d.name}.pt3")
            or chip_play(f"{d.name}.pt3")      # link-local drops 1st packets
            or chip_save(f"{d.name}.pt3", pt3.read_bytes(), play=True)):
        print(f"  ♪ ZX Spectrum Chip playing {d.name}")


_blanked = False                  # debounce for the blank-boot silencer


def on_console_event(ev, cart=None):
    """Serial-event hook for whoever owns the port: game-over (won or lost)
    silences the box; (re)entering play restarts the cartridge's theme."""
    global _blanked
    name = ev.get("ev") if isinstance(ev, dict) else None
    if name == "blank":               # cartridge evaporated — kill the theme
        if not _blanked:              # (blank re-announces every 2 s; stop once)
            chip_stop()
        _blanked = True
        return
    _blanked = False
    if name == "over":
        chip_stop()
    elif name == "play" and cart:
        play_for(Path(cart))


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        d = Path(arg)
        sc = json.loads((d / "theme.json").read_text())
        try:
            title = json.loads((d / "design.json").read_text())["title"]
        except Exception:
            title = d.name[4:]
        print(make_theme(d, sc, title))
