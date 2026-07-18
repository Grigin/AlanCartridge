"""The game ontology: Python rolls structured coordinates, the LLM only skins.

roll(history) -> coords dict with genre/objective/threat/twist/pace/setting,
concrete numeric params (winnable by construction), a filled-in genre spec
sheet for the implement prompt, verb + goal for the engine HUD, and a control
hint for the title card. Anti-repeat uses coords saved in library meta.json.
"""
import random

# axes

OBJECTIVES = {           # objective -> default HUD verb
    "collect": "CATCH", "destroy": "BLAST", "block": "BLOCK",
    "survive": "SURVIVE", "reach": "REACH", "stack": "STACK", "clear": "CLEAR",
}

THREATS = {
    "collision": "touching a hazard costs a life",
    "fall":      "falling / dropping / missing costs a life",
    "overwhelm": "every {slack} misses or mistakes cost a life",
    "timer":     "a deadline: miss it and lose a life, deadline extends",
}

TWISTS = {  # name -> (description for the spec, genres it fits)
    "surge":    ("every ~12s a 3s SPEED SURGE: all hazard speeds x1.5, telegraph it "
                 "by flashing the background PAL[2] one frame before",
                 ["catcher", "dodger", "racer", "shooter", "defender", "crosser", "breaker", "climber"]),
    "flip":     ("controls mirror (left<->right) while an indicator shows sprT(SPR_ARROW,...,8,SF_FLIPX); "
                 "3s on, 6s off",
                 ["catcher", "dodger", "crosser", "platformer", "snake", "sorter"]),
    "invert":   ("halfway to the goal, goods and bads swap sprites for the rest of the game "
                 "(announce with a 1s full-screen flash of PAL[10])",
                 ["catcher", "sorter", "collector", "snake"]),
    "shrink":   ("the playable zone / paddle / platform narrows by ~30% after each third of progress",
                 ["dodger", "defender", "stacker", "breaker", "climber", "crosser"]),
    "boss":     ("at progress >= half the goal, spawn ONE SF_BIG hazard worth 3 normal ones, "
                 "slower but tanky (3 hits) or unavoidable-unless-dodged",
                 ["shooter", "defender", "dodger", "platformer", "racer"]),
    "night":    ("light dims: only a radius ~34 circle around the player renders entities; "
                 "outside it draw them as sprT(...,1) shadows",
                 ["platformer", "snake", "crosser", "dodger"]),
    "double":   ("in the final third of progress the spawn period halves",
                 ["catcher", "shooter", "sorter", "defender", "racer"]),
    "movegoal": ("the goal objects themselves drift/flee at 40% of player speed",
                 ["collector", "catcher", "platformer", "stacker"]),
}

PACE = {  # multipliers applied to rolled params
    "chill":   {"speed": 0.85, "period": 1.2, "goal": 0.85},
    "steady":  {"speed": 1.0,  "period": 1.0, "goal": 1.0},
    "frantic": {"speed": 1.2,  "period": 0.85, "goal": 1.1},
}

SETTINGS = {  # palette + sprite scope; skin picks names/fiction inside this.
    # optional "avatars" overrides the global AVATARS pool for that setting.
    "dungeon":   {"bg": [0, 1], "accents": [2, 13],
                  "props": ["SPR_DOOR", "SPR_CRATE", "SPR_POT", "SPR_URN", "SPR_PILLAR",
                            "SPR_CANDLE", "SPR_LADDER", "SPR_GATE", "SPR_FURNACE", "SPR_THRONE"],
                  "foes": ["SPR_BAT", "SPR_SPIDER", "SPR_SLIME", "SPR_GHOST", "SPR_CUBE",
                           "SPR_SHADE", "SPR_MITE", "SPR_SPIKERAT", "SPR_WORMPINK"],
                  "goods": ["SPR_GEM", "SPR_KEY", "SPR_POTION", "SPR_RING", "SPR_COIN"]},
    "forest":    {"bg": [1, 3], "accents": [4, 11],
                  "props": ["SPR_TREE", "SPR_PINE", "SPR_BUSH", "SPR_SPROUT", "SPR_HOUSE", "SPR_FLOWER"],
                  "foes": ["SPR_FOX", "SPR_SNAKE", "SPR_GOBLIN", "SPR_SPIDER", "SPR_HOPPER",
                           "SPR_SHROOM", "SPR_TOADSTOOL", "SPR_WORM"],
                  "goods": ["SPR_STAR", "SPR_HEART", "SPR_RING", "SPR_KEY", "SPR_COIN"]},
    "village":   {"bg": [1, 5], "accents": [9, 4],
                  "props": ["SPR_HOUSE", "SPR_CASTLE", "SPR_TOWER", "SPR_WELL", "SPR_SIGN",
                            "SPR_FLAG", "SPR_DOOR", "SPR_TABLE", "SPR_DRESSER"],
                  "foes": ["SPR_IMP", "SPR_BRUTE", "SPR_GOBLIN", "SPR_JELLY", "SPR_CHICK"],
                  "goods": ["SPR_POT", "SPR_BELL", "SPR_GEM", "SPR_HEART", "SPR_COIN"]},
    "graveyard": {"bg": [0, 2], "accents": [3, 13],
                  "props": ["SPR_CROSS", "SPR_GRAVE", "SPR_STATUE", "SPR_CANDLE", "SPR_URN", "SPR_BUST"],
                  "foes": ["SPR_GHOST", "SPR_BAT", "SPR_SHADE", "SPR_WISP", "SPR_SLIME",
                           "SPR_BATTY", "SPR_GLOB"],
                  "goods": ["SPR_ORB", "SPR_POTION", "SPR_RING", "SPR_KEY"]},
    "coast":     {"bg": [1, 12], "accents": [15, 10],
                  "props": ["SPR_WATER", "SPR_PALM", "SPR_CLOUD", "SPR_SUN", "SPR_WELL"],
                  "foes": ["SPR_CRAB", "SPR_JELLY", "SPR_PUFF", "SPR_TURTLE", "SPR_DROPLET",
                           "SPR_PENGUIN"],
                  "goods": ["SPR_STAR", "SPR_GEM", "SPR_HOOP", "SPR_SHIELD", "SPR_BLUEGEM"]},
    "sky":       {"bg": [1, 13], "accents": [12, 10],
                  "props": ["SPR_CLOUD", "SPR_SUN", "SPR_ZAP", "SPR_BOLT", "SPR_TOWER"],
                  "foes": ["SPR_BAT", "SPR_WISP", "SPR_PUFF", "SPR_SHADE", "SPR_BLOB",
                           "SPR_DRONE", "SPR_DROPLET"],
                  "goods": ["SPR_STAR", "SPR_BOLT", "SPR_GEM", "SPR_HOOP"]},
    "speedway":  {"bg": [0, 5], "accents": [8, 10],
                  "props": ["SPR_BARRIER_RED", "SPR_BARRIER_WHT", "SPR_CONE", "SPR_CHEVRON",
                            "SPR_TIRES_RED", "SPR_TIRES_WHT", "SPR_PARKTREE", "SPR_GRATE",
                            "SPR_LANELINE"],
                  "foes": ["SPR_CAR_BLUE", "SPR_CAR_GREEN", "SPR_CAR_YELLOW", "SPR_CAR_BLACK",
                           "SPR_MOTO_GREEN", "SPR_OILSLICK", "SPR_BARREL_RED", "SPR_ROCK"],
                  "goods": ["SPR_FLAG", "SPR_STAR", "SPR_GEM", "SPR_COIN", "SPR_PENNANT"],
                  "avatars": ["SPR_CAR_RED", "SPR_MOTO_RED"]},
    "city":      {"bg": [1, 0], "accents": [9, 12],
                  "props": ["SPR_STREETLAMP", "SPR_HYDRANT", "SPR_MAILBOX", "SPR_BENCH",
                            "SPR_BIN", "SPR_CARTON", "SPR_CHAINLINK", "SPR_VENDING",
                            "SPR_BILLBOARD", "SPR_NEON", "SPR_CITYTREE", "SPR_BARRICADE",
                            "SPR_SIDEWALK", "SPR_CROSSWALK", "SPR_GASPUMP", "SPR_PARKMETER"],
                  "foes": ["SPR_CAR_BLACK", "SPR_CAR_BLUE", "SPR_MOTO_GREEN", "SPR_DRONE",
                           "SPR_SPIKERAT", "SPR_TRASHBAG"],
                  "goods": ["SPR_COIN", "SPR_BLUEGEM", "SPR_KEY", "SPR_AMMO", "SPR_PISTOL"],
                  "avatars": ["SPR_GUNNER", "SPR_COMMANDO", "SPR_CAR_RED"]},
}

AVATARS = ["SPR_VIKING", "SPR_DWARF", "SPR_KNIGHT", "SPR_HUNTER", "SPR_MONK",
           "SPR_GUARD", "SPR_ELF", "SPR_WIZARD", "SPR_BRUTE", "SPR_CYCLOPS"]

# genre -> setting preference weights (default 1); anti-repeat applies after
SETTING_WEIGHTS = {
    "racer":   {"speedway": 8, "city": 3},
    "crosser": {"city": 6, "speedway": 2},
    "platformer": {"forest": 2, "village": 2},
    "shooter": {"sky": 2, "city": 2},
}

# genres
# Each: objectives (with goal range), threats, params (name -> range), a
# winnability fix applied after the roll, and a spec template. Spec templates
# may reference any param plus {goal} {verb} {threat_line} {twist_line}.

GENRES = {
 "catcher": {
  "control": "dpad LR", "arena": "open floor, items fall",
  "objectives": {"collect": (8, 14)},
  "threats": ["collision", "overwhelm"],
  "params": {"pspeed": (55, 75), "period": (30, 45), "fall": (20, 32),
             "ramp": (6, 10), "bad_pct": (25, 40), "slack": (3, 4)},
  "hint": "DPAD: RUN UNDER THEM",
  "spec": """GENRE SPEC — CATCHER
Player (avatar sprite) runs along the bottom (y~66), dpad LR at {pspeed} px/s.
Items fall from the top: goods (a setting 'goods' sprite) and bads (a 'foes'
sprite), one spawn every {period} frames, {bad_pct}% bads, falling {fall} px/s
ramping +{ramp}% every 10s. Catch radius 10. eProgress(1) per good caught.
{threat_line}
Twist: {twist_line}
The engine draws score and goal — do NOT draw your own counters. Move feel:
continuous g_x += inp.dx * speed * dt. Flip the avatar with SF_FLIPX by
direction. Missed goods splash: 4 frames of sprT(good, x, y, 5)."""},

 "dodger": {
  "control": "dpad 4-way", "arena": "open field",
  "objectives": {"survive": (45, 70), "collect": (10, 16)},
  "threats": ["collision"],
  "params": {"pspeed": (60, 80), "n0": (3, 4), "nmax": (7, 9),
             "hspeed": (18, 28), "ramp": (8, 12)},
  "hint": "DPAD: DODGE",
  "spec": """GENRE SPEC — DODGER
Player moves 4-way in the arena (dpad, {pspeed} px/s, clamp inside walls).
Hazards (foes sprites) drift/bounce through: start {n0}, add one every 10s up
to {nmax}, speeds {hspeed} px/s ramping +{ramp}%/10s.
If objective is survive: eProgress(1) once per second (if (inp.t % 30 == 0)).
If objective is collect: goods appear one at a time at random spots,
eProgress(1) per pickup (radius 10).
{threat_line}
Twist: {twist_line}
Engine draws the HUD. Give hazards distinct movement personalities (bouncer,
chaser at 60% speed, sine-drifter). i-frames: 20 frames after a hit."""},

 "racer": {
  "control": "dpad UD lanes", "arena": "3 horizontal lanes scrolling left",
  "objectives": {"reach": (40, 65), "collect": (9, 14)},
  "threats": ["collision"],
  "params": {"lanes": (3, 3), "scroll": (55, 80), "period": (28, 42),
             "ramp": (7, 11), "slack": (3, 3)},
  "hint": "DPAD U/D: LANES",
  "spec": """GENRE SPEC — RACER
Side view. Player (avatar, SF_FLIPX so it faces right) fixed near x=28,
{lanes} lanes at y = 24/44/64; dpad U/D hops one lane (cooldown 6 frames).
The world scrolls left at {scroll} px/s: lane markers (dashes) plus setting
props in the background parallax at half speed. Obstacles (foes sprites)
arrive from the right in random lanes, one every {period} frames, speed =
scroll, ramping +{ramp}%/10s.
If objective is reach: eProgress(1) every 30 frames (distance).
If objective is collect: goods float in lanes between obstacles,
eProgress(1) per pickup.
{threat_line}
Twist: {twist_line}
Engine draws the HUD. Near-miss (passing within 4px) scores eScore(2).
If the setting kit provides vehicle sprites, avatar and traffic MUST be
vehicles (cars face right; oncoming traffic uses SF_FLIPX)."""},

 "shooter": {
  "control": "dpad LR + A fires", "arena": "fixed shooter, enemies above",
  "objectives": {"destroy": (10, 18)},
  "threats": ["collision", "overwhelm"],
  "params": {"pspeed": (60, 80), "cool": (8, 12), "bspeed": (90, 120),
             "period": (35, 55), "espeed": (14, 24), "ramp": (8, 12), "slack": (3, 4)},
  "hint": "DPAD: MOVE  A: FIRE",
  "spec": """GENRE SPEC — SHOOTER
Player at the bottom (avatar), dpad LR at {pspeed} px/s. A fires a bullet
(3x3 rect, {bspeed} px/s up, cooldown {cool} frames, max 3 alive).
Enemies (foes sprites, walk-frame pairs where available) spawn at the top
every {period} frames and descend {espeed} px/s in sine weave, ramp
+{ramp}%/10s. Bullet hit = eProgress(1) + eScore(5) + 4-frame sprT flash.
{threat_line}
Twist: {twist_line}
Engine draws the HUD. Do not let more than ~10 entities exist at once."""},

 "defender": {
  "control": "encoder rotates", "arena": "ring around a core",
  "objectives": {"block": (10, 16), "survive": (40, 60)},
  "threats": ["collision"],
  "params": {"radius": (24, 28), "period": (34, 50), "mspeed": (16, 26), "ramp": (8, 12)},
  "hint": "DIAL: SPIN SHIELD",
  "spec": """GENRE SPEC — DEFENDER
A core (SF_BIG sprite) sits at centre. The shield paddle orbits at radius
{radius}: g_ang += inp.enc * 0.35 (dpad LR as slow fallback). Hazards fly in
from the edges straight at the core, one every {period} frames at {mspeed}
px/s, ramp +{ramp}%/10s. Shield block (radius 10) = eProgress(1) + eScore(5)
+ SPR_BOOM flash. Core hit = eLoseLife() + red sprT flash of the core.
If objective is survive, eProgress(1) per second instead of per block.
{threat_line}
Twist: {twist_line}
Engine draws the HUD. This is the encoder's genre — the dial must matter."""},

 "sorter": {
  "control": "dpad or encoder toggles gate", "arena": "conveyor + 2 bins",
  "objectives": {"collect": (10, 16)},
  "threats": ["overwhelm"],
  "params": {"period": (40, 60), "speed": (26, 40), "ramp": (7, 10), "slack": (3, 4)},
  "verb": {"collect": "SORT"},
  "hint": "DPAD U/D: AIM CHUTE",
  "spec": """GENRE SPEC — SORTER
Items ride a conveyor from the right at {speed} px/s (ramp +{ramp}%/10s), one
every {period} frames, of TWO kinds (two distinct sprites). At the left, two
bins (top/bottom). dpad U/D (or encoder sign) sets the chute; the item routes
into the aimed bin when it reaches x=30. Correct bin = eProgress(1) +
eScore(5); wrong = counts toward the slack.
{threat_line}
Twist: {twist_line}
Engine draws the HUD. Draw the aimed chute clearly (thick line + arrow).
Preview: the NEXT item's kind blinks on its bin every 30 frames."""},

 "stacker": {
  "control": "A drops the mover", "arena": "tower grows from the floor",
  "objectives": {"stack": (8, 12)},
  "threats": ["fall"],
  "params": {"speed": (40, 68), "ramp": (10, 16), "wid0": (36, 44)},
  "hint": "A: DROP THE BLOCK",
  "spec": """GENRE SPEC — STACKER
A block (16x8 rect topped with a sprite) sweeps LR across the screen at
{speed} px/s (bounce at walls, +{ramp}% per placed block). A drops it: it
falls fast onto the tower. Overlap with the block below keeps only the
overlapping width (start width {wid0}px, min 8). eProgress(1) per placed
block; the camera-less tower compresses: shift all rows down 8px each place.
Missing the tower completely = {threat_line}
Twist: {twist_line}
Engine draws the HUD. Perfect (within 2px) alignment = eScore(10) + flash."""},

 "platformer": {
  "control": "dpad LR + A jumps", "arena": "3 platform layers + pits",
  "objectives": {"collect": (8, 12)},
  "threats": ["fall", "collision"],
  "params": {"pspeed": (55, 70), "jump": (150, 180), "grav": (380, 450),
             "n_en": (2, 3), "espeed": (16, 26)},
  "hint": "DPAD: RUN  A: JUMP",
  "spec": """GENRE SPEC — PLATFORMER
Gravity {grav} px/s2, jump impulse -{jump} px/s (A only when grounded), run
{pspeed} px/s. Build 3 platform layers (y=30/50/70) from filled rects with
1-2 gaps each (from GAME_SEED via rndi at init). Goods (goods sprites) sit
on platforms; eProgress(1) per pickup, then respawn it elsewhere. {n_en}
patrol enemies (foes, walk flip) pace platforms at {espeed} px/s.
{threat_line} Falling into a gap: eLoseLife() + respawn on the top layer.
Twist: {twist_line}
Engine draws the HUD. Squash the avatar 1 frame on landing (fillRect under)."""},

 "breaker": {
  "control": "encoder paddle", "arena": "brick grid above, paddle below",
  "objectives": {"clear": (12, 18)},
  "threats": ["fall"],
  "params": {"pwid": (24, 30), "bspeed": (55, 75), "ramp": (6, 9)},
  "verb": {"clear": "BREAK"},
  "hint": "DIAL: MOVE PADDLE",
  "spec": """GENRE SPEC — BREAKER
Paddle ({pwid}px wide, y=72) moves with the encoder: g_px += inp.enc * 6
(dpad LR fallback 2px/frame). Ball ({bspeed} px/s, +{ramp}%/10s) bounces off
walls/paddle; angle depends on where it strikes the paddle. {goal} bricks
(12x6 rects in 2-3 rows near the top, PAL colors by row, one sprite per ~4th
brick as a bonus brick worth eScore(10)). Brick hit = eProgress(1). Ball
below the paddle = {threat_line} then relaunch from the paddle.
Twist: {twist_line}
Engine draws the HUD. Never let the ball go fully horizontal (min |vy| 20)."""},

 "crosser": {
  "control": "dpad steps", "arena": "traffic lanes between two banks",
  "objectives": {"reach": (5, 9)},
  "threats": ["collision", "timer"],
  "params": {"lanes": (3, 4), "speed": (24, 40), "period": (30, 45),
             "ramp": (6, 10), "slack": (12, 15)},
  "verb": {"reach": "CROSS"},
  "hint": "DPAD: STEP ACROSS",
  "spec": """GENRE SPEC — CROSSER
Grid steps of 8px (dpad, 6-frame cooldown). Safe banks at the bottom (start)
and top. Between them {lanes} horizontal lanes with moving hazards (foes /
prop sprites), lane speeds {speed} px/s alternating direction, spawn every
{period} frames per lane, ramp +{ramp}%/10s. Reaching the top bank =
eProgress(1), teleport back to the bottom, lanes speed up 5%.
{threat_line} On hit: back to the bottom bank.
Twist: {twist_line}
Engine draws the HUD. Draw the two banks as prop-sprite rows.
If the setting kit provides vehicle sprites, the lane hazards MUST be
vehicles (they face right; leftward lanes use SF_FLIPX)."""},

 "snake": {
  "control": "dpad turns", "arena": "8px grid",
  "objectives": {"collect": (8, 14)},
  "threats": ["collision"],
  "params": {"step0": (9, 11), "stepmin": (5, 6), "grow": (2, 3)},
  "verb": {"collect": "EAT"},
  "hint": "DPAD: TURN",
  "spec": """GENRE SPEC — SNAKE
Grid 8px cells inside x 8..152, y 16..72. The snake advances one cell every
{step0} frames (speeding to every {stepmin} frames as it grows); dpad sets
direction (no 180 turns). Body = array of cell coords (max 40, that is
enough for the goal). Head draws as the avatar sprite SF_SMALL, body as 6x6
rects in two alternating PAL colors. One good (goods sprite, SF_SMALL) on a
free cell: eating = eProgress(1) + grow {grow} segments + respawn it.
Hitting a wall or your own body = {threat_line} then reset the snake to
length 3 in the centre (progress KEPT).
Twist: {twist_line}
Engine draws the HUD."""},

 "climber": {
  "control": "dpad LR steer", "arena": "platforms scroll down",
  "objectives": {"reach": (12, 18)},
  "threats": ["fall"],
  "params": {"pspeed": (60, 80), "bounce": (140, 170), "grav": (360, 430),
             "gapy": (18, 24)},
  "verb": {"reach": "CLIMB"},
  "hint": "DPAD: STEER THE HOPS",
  "spec": """GENRE SPEC — CLIMBER
Auto-bounce: the avatar always bounces off any platform it lands on (impulse
-{bounce} px/s, gravity {grav} px/s2); dpad LR steers at {pspeed} px/s, wrap
around screen edges LR. Platforms are 26x4 rects every {gapy}px of height,
random x (from rndi). When the player is above mid-screen, scroll the world
down so it stays centred; each NEW highest platform reached = eProgress(1).
Falling below the bottom edge = {threat_line} then respawn bouncing on the
lowest visible platform (progress KEPT).
Twist: {twist_line}
Engine draws the HUD. Decorate every 4th platform with a prop sprite."""},
}

# "collector" appears in twist masks as an alias genre; map it to dodger-collect
_TWIST_ALIAS = {"collector": "dodger"}


def _fit_twists(genre):
    out = []
    for name, (desc, mask) in TWISTS.items():
        genres = [_TWIST_ALIAS.get(g, g) for g in mask]
        if genre in genres:
            out.append(name)
    return out


def _no_repeat(pool, recent):
    fresh = [p for p in pool if p not in recent]
    return fresh or list(pool)


def roll(history, rng=None):
    """history: list of coords dicts (newest last). Returns coords."""
    rng = rng or random.Random()

    genres = _no_repeat(list(GENRES), [h.get("genre") for h in history[-4:]])
    genre = rng.choice(genres)
    G = GENRES[genre]

    pairs = [h.get("genre_objective") for h in history[-8:]]
    objs = ([o for o in G["objectives"] if f"{genre}/{o}" not in pairs]
            or list(G["objectives"]))
    objective = rng.choice(objs)

    threat = rng.choice(G["threats"])
    twist = rng.choice(_no_repeat(_fit_twists(genre), [h.get("twist") for h in history[-3:]]))
    pace = rng.choice(list(PACE))
    pool = _no_repeat(list(SETTINGS), [h.get("setting") for h in history[-3:]])
    w = SETTING_WEIGHTS.get(genre, {})
    setting = rng.choices(pool, weights=[w.get(s, 1) for s in pool])[0]
    avatar = rng.choice(SETTINGS[setting].get("avatars", AVATARS))

    p = {k: rng.randint(a, b) for k, (a, b) in G["params"].items()}
    mult = PACE[pace]
    for k in p:
        if k in ("period", "cool", "step0", "stepmin"):
            p[k] = max(1, round(p[k] * mult["period"]))
        elif k in ("pspeed", "speed", "scroll", "fall", "hspeed", "espeed",
                   "mspeed", "bspeed", "bounce"):
            p[k] = round(p[k] * mult["speed"])

    lo, hi = G["objectives"][objective]
    goal = round(rng.randint(lo, hi) * mult["goal"])
    goal = max(lo, min(goal, hi + 2))

    # winnability by construction: cap count-goals by what the spawn economy
    # can deliver in ~75s of 60%-efficient play
    if objective in ("collect", "destroy", "block") and "period" in p:
        supply = 75 * 30 / p["period"]
        if "bad_pct" in p:
            supply *= (1 - p["bad_pct"] / 100)
        goal = max(5, min(goal, int(supply * 0.6)))

    verb = G.get("verb", {}).get(objective, OBJECTIVES[objective])
    threat_line = THREATS[threat].format(slack=p.get("slack", 3))
    if threat == "timer":
        threat_line = (f"a deadline: reach the next crossing within {p.get('slack', 12)}s "
                       "or eLoseLife(); the timer resets each crossing")
    twist_line = TWISTS[twist][0]
    spec = G["spec"].format(goal=goal, verb=verb, threat_line=threat_line,
                            twist_line=twist_line, **p)
    spec += (f"\nGoal: {verb} {goal} -> define GAME_GOAL {goal}, GAME_VERB \"{verb}\", "
             f"call eProgress as specified; the engine ends the game at the goal.")

    return {
        "genre": genre, "objective": objective, "genre_objective": f"{genre}/{objective}",
        "verb": verb, "goal": goal, "threat": threat, "twist": twist, "pace": pace,
        "setting": setting, "avatar": avatar, "params": p,
        "setting_kit": SETTINGS[setting], "hint": G["hint"], "spec": spec,
    }


if __name__ == "__main__":
    import collections, json, re, sys
    from pathlib import Path

    ids = set(re.findall(r"SPR_[A-Z0-9_]+",
                         (Path(__file__).parent / "forge_sketch/sprites.h").read_text()))
    for s, kit in SETTINGS.items():
        for role in ("props", "foes", "goods"):
            missing = [n for n in kit[role] if n not in ids]
            assert not missing, f"{s}.{role} references missing sprites: {missing}"
        missing = [n for n in kit.get("avatars", []) + AVATARS if n not in ids]
        assert not missing, f"{s} avatars missing: {missing}"
    print("all kit/avatar sprite references exist in sprites.h")

    hist, seen, setg = [], collections.Counter(), collections.Counter()
    rng = random.Random(7)
    for i in range(200):
        c = roll(hist, rng)
        seen[c["genre"]] += 1
        if c["genre"] in ("racer", "crosser"):
            setg[c["setting"]] += 1
        assert c["objective"] in GENRES[c["genre"]]["objectives"], "bad pair"
        assert c["genre"] not in [h["genre"] for h in hist[-4:]], "genre repeat"
        assert "{" not in c["spec"], "unfilled spec placeholder"
        hist.append(c)
    print("genre distribution over 200 rolls:", dict(seen))
    print("racer/crosser settings:", dict(setg))
    print(json.dumps({k: v for k, v in roll(hist, rng).items()
                      if k not in ("spec", "setting_kit")}, indent=1))
    if "-v" in sys.argv:
        print(roll(hist, rng)["spec"])
