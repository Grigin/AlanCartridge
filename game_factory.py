import json
import re

import anthropic

from config import CONTRACT, GAME_EXAMPLES, MODEL, SKETCH

SPRITE_IDS = (set(re.findall(r"SPR_[A-Z0-9_]+", (SKETCH / "sprites.h").read_text()))
              - {"SPR_COUNT", "SPR_PX"})

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _system():
    blocks = [{"type": "text", "text": CONTRACT}]
    for i, path in enumerate(GAME_EXAMPLES):
        tag = ("complete correct game" if i == 0 and len(GAME_EXAMPLES) > 1
               else "target depth — match this")
        blocks.append({"type": "text",
                       "text": f"Example ({tag}):\n\n{path.read_text()}"})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}  # caches the whole prefix
    return blocks




def ask(prompt, max_tokens=8000, temperature=1.0):
    r = _get_client().messages.create(
        model=MODEL, max_tokens=max_tokens, temperature=temperature,
        system=_system(), messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if b.type == "text")


def strip_fence(s, lang=""):
    m = re.search(r"```(?:%s|json|cpp|c\+\+|arduino)?\s*\n(.*?)```" % lang, s, re.S)
    if m:
        return m.group(1).strip()
    # unterminated fence = truncated response; still strip the fence header
    s = re.sub(r"^\s*```[a-z+]*\s*\n", "", s)
    return s.replace("```", "").strip()


def parse_json(s):
    """First balanced JSON object in s; tolerates prose around it. ValueError on failure."""
    s = strip_fence(s)
    i = s.find("{")
    if i < 0:
        raise ValueError("no JSON object in response")
    try:
        obj, _ = json.JSONDecoder().raw_decode(s[i:])
    except json.JSONDecodeError as e:
        raise ValueError(f"unparseable JSON ({e.msg} at char {e.pos})") from None
    return obj


def theme_steer(theme, genres, settings):
    """Map a theme to its best-fitting genre and setting (pre-roll steering).
    Returns (genre|None, setting|None); Nones mean 'roll normally'."""
    try:
        out = parse_json(ask(
            f"Theme for a tiny arcade game: {theme}\n"
            f"Pick the SINGLE best-fitting genre and setting for this theme.\n"
            f"Genres: {genres}\nSettings: {settings}\n"
            'Respond with ONLY JSON: {"genre": "...", "setting": "..."}',
            max_tokens=200, temperature=0.4))
    except ValueError:
        return None, None
    g, s = out.get("genre"), out.get("setting")
    return (g if g in genres else None), (s if s in settings else None)


def skin(coords, theme, hist, fix=None):
    """One creative pass over Python-rolled coordinates. Coords are immutable.
    fix: design_check errors from a previous attempt to correct explicitly."""
    kit = coords["setting_kit"]
    titles = [h.get("title", "?") for h in hist[-8:]]
    prompt = (
        "Dress this rolled game skeleton in fiction. The COORDINATES ARE FIXED "
        "— do not change genre, objective, numbers or setting.\n"
        f"COORDS: genre={coords['genre']}, objective={coords['objective']} "
        f"(goal {coords['goal']}, HUD verb {coords['verb']}), "
        f"twist={coords['twist']}, pace={coords['pace']}, "
        f"setting={coords['setting']}, player avatar={coords['avatar']}\n"
        f"Sprites in scope — props: {kit['props']} foes: {kit['foes']} "
        f"goods: {kit['goods']}\n"
        "Respond with ONLY a JSON object:\n"
        '{"title":"<= 12 chars ALL CAPS",'
        '"blurb":"<= 45 chars of flavor; objective line is shown automatically",'
        f'"hint":"<= 20 chars control hint, base it on: {coords["hint"]}",'
        '"entities":[{"name","behavior","sprite":"SPR_* from the in-scope lists"}],'
        '"twist_flavor":"one sentence naming the twist in-fiction",'
        '"map":["8 strings of EXACTLY 20 chars — the level, top row first"],'
        '"legend":{"single letter":"SPR_* decor sprite from the props list"}}\n'
        "LEVEL MAP rules: chars are '.' empty, '#' solid terrain, 'P' player "
        "start (exactly one), 'G' goal spots, 'S' hazard spawns, plus 1-3 "
        "legend letters for decor. You may ALSO put \"#\" in the legend to "
        "texture solid terrain with a sprite (terrain-group sprites like "
        "SPR_BLOCKX/SPR_SIDEWALK/SPR_GRASS work well; untextured solids "
        "render grey). Solids under 45% of cells. Compose deliberately — "
        "clusters, rhythm, sightlines — not noise.\n"
        f"Map brief for this genre: {coords.get('map_brief', 'decorate the edges, P at start')}\n"
        f"Titles already used (do not echo them): {titles}\n"
        "Ground it in the setting, then break ONE expectation. You may pull "
        "ONE signature sprite from the full catalog beyond the in-scope lists."
    )
    if coords.get("wild"):
        prompt += "\n" + coords["wild"]
    if theme:
        prompt += (f"\nAudience theme (must be honoured): {theme}\n"
                   "Because a theme is set, you MAY replace \"avatar\" with any "
                   "SPR_* from the full catalog that fits the theme better — "
                   "add it to your JSON as \"avatar\".")
    if fix:
        prompt += (f"\nYOUR PREVIOUS ATTEMPT WAS REJECTED: {fix}. Fix exactly "
                   "these issues (count characters!) and keep the same spirit.")
    out = parse_json(ask(prompt, max_tokens=4000, temperature=1.0))
    merged = {**out, **{k: v for k, v in coords.items() if k != "setting_kit"}}
    merged["sprites_in_scope"] = kit
    if theme and isinstance(out.get("avatar"), str) and out["avatar"]:
        merged["avatar"] = out["avatar"]      # themed recast (validated later)
    # flavor fields are display-only — trim instead of burning a reskin round
    b = str(merged.get("blurb", ""))
    if len(b) > 46:                        # word-boundary trim, last resort
        b = (b[:47].rsplit(" ", 1)[0] or b[:46]).rstrip(" ,.;:!")
    merged["blurb"] = b
    merged["hint"] = str(merged.get("hint", coords["hint"]))[:20]
    # LLMs miscount characters: normalize near-miss maps instead of rejecting
    if isinstance(merged.get("map"), list):
        rows = [(str(r) + "." * 20)[:20] for r in merged["map"][:8]]
        merged["map"] = rows + ["." * 20] * (8 - len(rows))
    return merged


def compose(des, recent=None):
    """8-bit theme score for a finished design. Retries once on check()
    errors from music.score, then raises ValueError (game ships silent)."""
    from music.score import check
    prompt = (
        "Compose the looping theme tune for this game as a chip-music score. "
        "It plays on a real ZX Spectrum AY-3-8912 (3 square channels + noise) "
        "beside the console while the game runs.\n"
        f"GAME: {des['title']} — {des.get('blurb', '')}. "
        f"Setting {des.get('setting')}, genre {des.get('genre_objective')}, "
        f"pace {des.get('pace')}, twist {des.get('twist')}.\n"
        "Respond with ONLY JSON:\n"
        '{"tempo": <bpm 70-200, match the pace>,\n'
        ' "flavor": {"style": "chiptune|faithful", '
        '"bass": "normal|envelope|envelope-tone", '
        '"arps": bool, "echo": bool, "vibrato": bool},\n'
        ' "lead": [[pitch, start, dur, vel], ...],\n'
        ' "bass": [[pitch, start, dur, vel], ...],\n'
        ' "harmony": [[pitch, start, dur, vel], ...]  (optional),\n'
        ' "drums": [["K"|"S"|"H"|"O", start], ...]  (optional; kick/snare/'
        "hat/open-hat)}\n"
        'RULES: pitch is a name like "C4"/"F#3"/"Bb2", range A1..C7. '
        "start/dur are SIXTEENTH-grid integers from 0 (4 sixteenths = 1 beat). "
        "8-16 bars (128-256 sixteenths) that loop seamlessly. vel 1-127 shapes "
        "dynamics. Keep the lead STRICTLY the highest voice and the bass "
        "STRICTLY the lowest — the arranger splits voices by register. "
        "Write a real melody: a hook, an answering phrase, a varied repeat — "
        "not a scale. Bass grooves on chord roots; drums drive the pace. "
        "arps and echo are only heard when you write no drums."
    )
    if recent:
        prompt += ("\nRecent themes (vary key, tempo and flavor from these): "
                   + json.dumps(recent))
    errs = []
    for _ in (1, 2):
        p = prompt if not errs else (
            prompt + "\nYOUR PREVIOUS SCORE WAS REJECTED: "
            + "; ".join(errs)[:300] + ". Fix exactly these issues.")
        try:
            sc = parse_json(ask(p, max_tokens=6000, temperature=1.0))
            errs = check(sc)
        except ValueError as e:
            errs = [str(e)]
        if not errs:
            return sc
    raise ValueError("; ".join(errs)[:200])


def design_check(des):
    """Non-LLM gate on the skinned design."""
    errs = []
    if not 0 < len(des.get("title", "")) <= 12:
        errs.append("title missing or > 12 chars")
    if len(des.get("blurb", "")) > 46:
        errs.append("blurb > 46 chars")
    if not 0 < len(des.get("hint", "")) <= 20:
        errs.append("hint missing or > 20 chars")
    if not des.get("entities"):
        errs.append("no entities")
    for e in des.get("entities", []):
        s = e.get("sprite", "")
        if s and s not in SPRITE_IDS:
            errs.append(f"unknown sprite {s}")
    if des.get("avatar") not in SPRITE_IDS:
        errs.append(f"unknown avatar {des.get('avatar')}")
    m, leg = des.get("map"), des.get("legend") or {}
    if not (isinstance(m, list) and len(m) == 8
            and all(isinstance(r, str) and len(r) == 20 for r in m)):
        errs.append("map must be exactly 8 rows of exactly 20 chars")
    else:
        flat = "".join(m)
        bad = sorted({ch for ch in flat if ch not in ".#PGS" and ch not in leg})
        if bad:
            errs.append(f"map chars missing from legend: {bad}")
        if flat.count("P") != 1:
            errs.append(f"map needs exactly one P (has {flat.count('P')})")
        if flat.count("#") > 72:
            errs.append("map over 45% solid — open it up")
        if sum(ch != "." for ch in flat) < 8:
            errs.append("map nearly empty — compose a level")
    for k, v in leg.items():
        if len(k) != 1 or k in ".PGS":
            errs.append(f"bad legend key {k!r}")
        elif v not in SPRITE_IDS:
            errs.append(f"unknown legend sprite {v}")
    return errs


def map_code(des):
    """C constants for the validated map — appended to game.ino by the forge."""
    rows, leg = des.get("map"), des.get("legend") or {}
    if not (isinstance(rows, list) and len(rows) == 8
            and all(isinstance(r, str) and len(r) == 20 for r in rows)):
        rows = ["." * 20] * 4 + ["." * 9 + "P" + "." * 10] + ["." * 20] * 3
        leg = {}                              # invalid map -> empty fallback
    flat = "".join(rows)
    if flat.count("P") != 1:                  # guarantee exactly one start
        rows = [r.replace("P", ".") for r in rows]
        for r in (6, 5, 7, 4, 3):             # free cell near bottom-centre
            for c in (9, 10, 8, 11, 7, 12, 6, 13):
                if rows[r][c] == ".":
                    rows[r] = rows[r][:c] + "P" + rows[r][c + 1:]
                    break
            else:
                continue
            break
    leg = {k: v for k, v in leg.items() if len(k) == 1 and k not in ".PGS"}
    keys = "".join(sorted(leg))
    sprs = ", ".join(leg[k] for k in sorted(leg)) or "0"
    body = "\n".join(f'  "{r}"' for r in rows)
    return ("\n// level map — generated by the forge from the design, do not edit\n"
            f"const char* GAME_MAP =\n{body};\n"
            f"const char* GAME_MAP_KEYS = \"{keys}\";\n"
            f"const int   GAME_MAP_SPR[] = {{{sprs}}};\n")


def _body(des):
    return {k: v for k, v in des.items() if k != "spec"}


def implement(des):
    return strip_fence(ask(
        "Implement this design as game.ino per the contract. Follow the GENRE "
        "SPEC exactly — its numbers and eProgress rules are mandatory. "
        "Aim for 120-180 lines; over 260 is auto-rejected. "
        "The GAME_MAP constants are appended automatically — NEVER define "
        "GAME_MAP/GAME_MAP_KEYS/GAME_MAP_SPR yourself; the engine draws the "
        "map and background. Use mapSolid/mapX/mapY/mapCount as the spec says "
        "(the design's map rows are your reference for the layout). "
        "Return ONLY one ```cpp block.\n\n" + des.get("spec", "")
        + "\n\nDESIGN:\n" + json.dumps(_body(des), indent=1),
        max_tokens=16000, temperature=0.6),
        "cpp")


def repair(code, errors, des):
    return strip_fence(ask(
        "This game.ino was rejected. Fix it minimally and return the COMPLETE "
        "corrected file in ONE ```cpp block. Never add GAME_MAP constants — "
        "they are appended automatically.\n\n" + des.get("spec", "")
        + "\n\nDESIGN:\n" + json.dumps(_body(des))
        + "\n\nCODE:\n```cpp\n" + code + "\n```\n\nERRORS:\n" + errors[:4000],
        max_tokens=16000, temperature=0.6),
        "cpp")


BANNED = [r"\bdelay\s*\(", r"\bwhile\b", r"\bgoto\b", r"\bmalloc\b", r"\bnew\s",
          r"\bmillis\s*\(", r"#\s*include", r"\bString\b", r"\btft\b", r"\bmatrix\."]
REQUIRED = ["GAME_TITLE", "GAME_BLURB", "GAME_SEED", "GAME_LIVES",
            "GAME_GOAL", "GAME_VERB", "GAME_HINT", "GAME_BG", "GAME_MAP",
            "eProgress", "gameInit", "gameUpdate", "gameDraw"]

def _code_only(code):
    lines, out, in_block = code.splitlines(), [], False
    for ln in lines:
        if in_block:
            if "*/" in ln:
                ln, in_block = ln.split("*/", 1)[1], False
            else:
                out.append("")
                continue
        ln = re.sub(r'"(?:\\.|[^"\\])*"', '""', ln)
        ln = re.sub(r"'(?:\\.|[^'\\])*'", "''", ln)
        while "/*" in ln:
            pre, rest = ln.split("/*", 1)
            if "*/" in rest:
                ln = pre + rest.split("*/", 1)[1]
            else:
                ln, in_block = pre, True
        out.append(ln.split("//", 1)[0])
    return out


def static_check(code):
    clean = _code_only(code)
    src = code.splitlines()
    errs = []
    for pat in BANNED:
        for n, ln in enumerate(clean, 1):
            if re.search(pat, ln):
                errs.append(f"banned `{pat}` on line {n}: {src[n-1].strip()}")
                break
    errs += [f"missing required symbol: {s}" for s in REQUIRED if s not in code]
    joined = "\n".join(clean)
    if joined.count("{") != joined.count("}"):
        errs.append(f"unbalanced braces ({joined.count('{')} vs "
                    f"{joined.count('}')}) — file truncated? finish the code")
    if len(clean) > 260:
        errs.append("too long (>260 lines)")
    return errs
