"""Everything tokens: design, implement, repair, and the static contract gate."""
import json
import re

import anthropic

from config import CONTRACT, GAME_EXAMPLES, MODEL

MECH_BINS = ["dodge", "catch", "chase", "aim", "defend", "sort", "build",
             "rhythm", "memory", "balance", "herd", "race"]

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


def design(theme, hist):
    used = [m for _, m, _ in hist]
    fresh = [b for b in MECH_BINS if b not in used[-5:]] or MECH_BINS
    prompt = (
        "Design ONE new game for this console. Respond with ONLY a JSON object:\n"
        '{"title","blurb","genre","setting","characters":[{"name","role"}],'
        '"entities":[{"name","behavior"}],"mechanic","twist","controls",'
        '"win_condition","lose_condition","difficulty_ramp","lives":int,"seed":int}\n'
        f"Previously made (do NOT repeat a mechanic from the last 5): {hist[-8:]}\n"
        f"Pick your mechanic from these under-used bins: {fresh}\n"
        "Include at least 2 distinct moving entity behaviours and a twist — "
        "one rule that changes mid-game.\n"
        "title <= 12 chars ALL CAPS, blurb <= 24 chars. Mechanic must be "
        "expressible with d-pad + optional encoder. Be weird, be specific."
    )
    if theme:
        prompt += f"\nAudience theme (must be honoured): {theme}"
    return json.loads(strip_fence(ask(prompt, max_tokens=1500)))


def implement(des):
    return strip_fence(ask(
        "Implement this design as game.ino per the contract. "
        "Return ONLY one ```cpp block.\n\nDESIGN:\n" + json.dumps(des, indent=1)),
        "cpp")


def repair(code, errors, des):
    return strip_fence(ask(
        "This game.ino was rejected. Fix it minimally and return the COMPLETE "
        "corrected file in ONE ```cpp block.\n\nDESIGN:\n" + json.dumps(des)
        + "\n\nCODE:\n```cpp\n" + code + "\n```\n\nERRORS:\n" + errors[:4000]),
        "cpp")


BANNED = [r"\bdelay\s*\(", r"\bwhile\b", r"\bgoto\b", r"\bmalloc\b", r"\bnew\s",
          r"\bmillis\s*\(", r"#\s*include", r"\bString\b", r"\btft\b", r"\bmatrix\."]
REQUIRED = ["GAME_TITLE", "GAME_BLURB", "GAME_SEED", "GAME_LIVES",
            "gameInit", "gameUpdate", "gameDraw"]


def static_check(code):
    errs = [f"banned pattern: {p}" for p in BANNED if re.search(p, code)]
    errs += [f"missing required symbol: {s}" for s in REQUIRED if s not in code]
    if code.count("\n") > 220:
        errs.append("too long (>220 lines)")
    return errs
