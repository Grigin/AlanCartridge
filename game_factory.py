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
        tag = ("minimal correct game" if i == 0 and len(GAME_EXAMPLES) > 1
               else "target depth — match this")
        blocks.append({"type": "text",
                       "text": f"Example ({tag}):\n\n{path.read_text()}"})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}  # caches the whole prefix
    return blocks




def ask(prompt, max_tokens=4000):
    r = _get_client().messages.create(
        model=MODEL, max_tokens=max_tokens, system=_system(),
        messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if b.type == "text")


def strip_fence(s, lang=""):
    m = re.search(r"```(?:%s|json|cpp|c\+\+|arduino)?\s*\n(.*?)```" % lang, s, re.S)
    return (m.group(1) if m else s).strip()


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
        '"blurb":"<= 24 chars of flavor; objective line is shown automatically",'
        f'"hint":"<= 20 chars control hint, base it on: {coords["hint"]}",'
        '"entities":[{"name","behavior","sprite":"SPR_* from the in-scope lists"}],'
        '"twist_flavor":"one sentence naming the twist in-fiction"}\n'
        f"Titles already used (do not echo them): {titles}\n"
        "Be weird, be specific, stay inside the setting."
    )
    if theme:
        prompt += f"\nAudience theme (must be honoured): {theme}"
    if fix:
        prompt += (f"\nYOUR PREVIOUS ATTEMPT WAS REJECTED: {fix}. Fix exactly "
                   "these issues (count characters!) and keep the same spirit.")
    out = json.loads(strip_fence(ask(prompt, max_tokens=900)))
    merged = {**out, **{k: v for k, v in coords.items() if k != "setting_kit"}}
    merged["sprites_in_scope"] = kit
    # flavor fields are display-only — clamp instead of burning a reskin round
    merged["blurb"] = str(merged.get("blurb", ""))[:24]
    merged["hint"] = str(merged.get("hint", coords["hint"]))[:20]
    return merged


def design_check(des):
    """Non-LLM gate on the skinned design."""
    errs = []
    if not 0 < len(des.get("title", "")) <= 12:
        errs.append("title missing or > 12 chars")
    if len(des.get("blurb", "")) > 24:
        errs.append("blurb > 24 chars")
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
    return errs


def _body(des):
    return {k: v for k, v in des.items() if k != "spec"}


def implement(des):
    return strip_fence(ask(
        "Implement this design as game.ino per the contract. Follow the GENRE "
        "SPEC exactly — its numbers and eProgress rules are mandatory. "
        "Aim for 120-180 lines; over 260 is auto-rejected. "
        "Return ONLY one ```cpp block.\n\n" + des.get("spec", "")
        + "\n\nDESIGN:\n" + json.dumps(_body(des), indent=1)),
        "cpp")


def repair(code, errors, des):
    return strip_fence(ask(
        "This game.ino was rejected. Fix it minimally and return the COMPLETE "
        "corrected file in ONE ```cpp block.\n\n" + des.get("spec", "")
        + "\n\nDESIGN:\n" + json.dumps(_body(des))
        + "\n\nCODE:\n```cpp\n" + code + "\n```\n\nERRORS:\n" + errors[:4000]),
        "cpp")


BANNED = [r"\bdelay\s*\(", r"\bwhile\b", r"\bgoto\b", r"\bmalloc\b", r"\bnew\s",
          r"\bmillis\s*\(", r"#\s*include", r"\bString\b", r"\btft\b", r"\bmatrix\."]
REQUIRED = ["GAME_TITLE", "GAME_BLURB", "GAME_SEED", "GAME_LIVES",
            "GAME_GOAL", "GAME_VERB", "GAME_HINT", "eProgress",
            "gameInit", "gameUpdate", "gameDraw"]

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
    if len(clean) > 260:
        errs.append("too long (>260 lines)")
    return errs
