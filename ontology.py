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
    "frantic": {"speed": 1.12, "period": 0.9, "goal": 1.1},
}

DISABLED_GENRES = {"sorter",   # rolled out of the rotation: plays boring
                   "snake", "stacker"}   # generated games too bug-prone (a
                                         # stacker panic-rebooted the console
                                         # at game-over, 19 Jul)

# ── wildcards: controlled chaos, rolled by Python ───────────────────────────
WILD_P = 0.25          # chance a game goes wild (never two in a row)

MUTATORS = [  # (name, skin line, mechanical spec line)
 ("miniature", "the whole world is tiny",
  "draw ALL entities except the player with SF_SMALL (collision radius ~4); "
  "keep counts and speeds unchanged"),
 ("giants", "the foes are lumbering giants",
  "draw foes with SF_BIG (collision radius ~14) at 70% speed and 30% fewer"),
 ("nightshift", "it is the dead of night",
  "set GAME_BG = 0 (overrides the setting bg) and draw foes as sprT(...,13) "
  "silhouettes; goods stay in full color"),
 ("skittish", "the goods are alive and afraid",
  "goods drift away from the player at 30% of player speed, clamped to walls"),
 ("slippery", "the ground is slick ice",
  "player movement has momentum: accelerate and brake at 60% (same top speed)"),
 ("swarm", "many, but meek",
  "double the hazard count/spawn rate but run hazards at 70% speed"),
 ("mirror", "a mirrored dimension",
  "draw all foes and map decor with SF_FLIPX; controls stay normal"),
]

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
                            "SPR_FLAG", "SPR_DOOR", "SPR_TABLE", "SPR_DRESSER",
                            "SPR_LATTICE", "SPR_LATTICE_H", "SPR_LATTICE_V", "SPR_LATTICE_X"],
                  "foes": ["SPR_IMP", "SPR_BRUTE", "SPR_GOBLIN", "SPR_JELLY", "SPR_CHICK",
                           "SPR_GOOSE"],
                  "goods": ["SPR_POT", "SPR_BELL", "SPR_GEM", "SPR_HEART", "SPR_COIN"]},
    "graveyard": {"bg": [0, 2], "accents": [3, 13],
                  "props": ["SPR_CROSS", "SPR_GRAVE", "SPR_STATUE", "SPR_CANDLE", "SPR_URN", "SPR_BUST"],
                  "foes": ["SPR_GHOST", "SPR_BAT", "SPR_SHADE", "SPR_WISP", "SPR_SLIME",
                           "SPR_BATTY", "SPR_GLOB"],
                  "goods": ["SPR_ORB", "SPR_POTION", "SPR_RING", "SPR_KEY"]},
    "coast":     {"bg": [1, 12], "accents": [15, 10],
                  "props": ["SPR_WATER", "SPR_PALM", "SPR_CLOUD", "SPR_SUN", "SPR_WELL",
                            "SPR_GALLEON", "SPR_IRONSHIP"],
                  "foes": ["SPR_CRAB", "SPR_JELLY", "SPR_PUFF", "SPR_TURTLE", "SPR_DROPLET",
                           "SPR_PENGUIN", "SPR_GOOSE"],
                  "goods": ["SPR_STAR", "SPR_GEM", "SPR_HOOP", "SPR_SHIELD", "SPR_BLUEGEM"]},
    "sky":       {"bg": [1, 13], "accents": [12, 10],
                  "props": ["SPR_CLOUD", "SPR_SUN", "SPR_ZAP", "SPR_BOLT", "SPR_TOWER"],
                  "foes": ["SPR_BAT", "SPR_WISP", "SPR_PUFF", "SPR_SHADE", "SPR_BLOB",
                           "SPR_DRONE", "SPR_DROPLET"],
                  "goods": ["SPR_STAR", "SPR_BOLT", "SPR_GEM", "SPR_HOOP"]},
    "speedway":  {"bg": [0, 5], "accents": [8, 10],
                  "props": ["SPR_BARRIER_RED", "SPR_BARRIER_WHT", "SPR_CONE", "SPR_CHEVRON",
                            "SPR_TIRES_RED", "SPR_TIRES_WHT", "SPR_PARKTREE", "SPR_GRATE",
                            "SPR_LANELINE", "SPR_FINISH", "SPR_TRACKEDGE", "SPR_CONESTACK",
                            "SPR_CHEVRON_W", "SPR_YLINES_V",
                            "SPR_ROAD_LANES", "SPR_ROAD_LANES_V", "SPR_ROAD_LINE_V",
                            "SPR_ROAD_LINE_V2", "SPR_ROAD_DASHES", "SPR_ROAD_DASH_BEND",
                            "SPR_ROAD_CORNER_NE", "SPR_ROAD_CORNER_SE", "SPR_ROAD_CORNER_SW",
                            "SPR_ROAD_BRANCH", "SPR_ROAD_BRANCH2", "SPR_YLINE_TOP2",
                            "SPR_YLINES_V2", "SPR_YLINES_V3", "SPR_ASPHALT2",
                            "SPR_WLINE_E", "SPR_WLINE_W", "SPR_WLINE_S", "SPR_WLINE_V2"],
                  "foes": ["SPR_CAR_BLUE", "SPR_CAR_GREEN", "SPR_CAR_YELLOW", "SPR_CAR_BLACK",
                           "SPR_MOTO_GREEN", "SPR_MOTO_YELLOW", "SPR_MOTO_BLUE",
                           "SPR_OILSLICK", "SPR_BARREL_RED", "SPR_ROCK", "SPR_CONE_DOWN",
                           "SPR_CITYCAR_S"],
                  "goods": ["SPR_FLAG", "SPR_STAR", "SPR_GEM", "SPR_COIN", "SPR_PENNANT"],
                  "avatars": ["SPR_CAR_RED", "SPR_MOTO_RED"]},
    "city":      {"bg": [1, 0], "accents": [9, 12],
                  "props": ["SPR_STREETLAMP", "SPR_HYDRANT", "SPR_MAILBOX", "SPR_BENCH",
                            "SPR_BIN", "SPR_CARTON", "SPR_CHAINLINK", "SPR_VENDING",
                            "SPR_BILLBOARD", "SPR_NEON", "SPR_CITYTREE", "SPR_BARRICADE",
                            "SPR_SIDEWALK", "SPR_CROSSWALK", "SPR_GASPUMP", "SPR_PARKMETER",
                            "SPR_TRAFFICLIGHT", "SPR_STREETPOLE", "SPR_GARAGEDOOR",
                            "SPR_CRACKED", "SPR_CROSSWALK_V", "SPR_YLINE_V",
                            "SPR_TRAFFIC", "SPR_TRAFFIC2", "SPR_WHITECAR", "SPR_WHITECAR_B",
                            "SPR_WHITEVAN", "SPR_WHITEVAN_B", "SPR_BOXTRUCK", "SPR_TRAILER",
                            "SPR_SCHOOLKID", "SPR_PASSERBY", "SPR_FLATCAP",
                            "SPR_REDBRICK2", "SPR_BRICKPIPE2", "SPR_CANOPY_O2",
                            "SPR_STEELPANEL", "SPR_WBARS_H", "SPR_WCORNER_SE",
                            "SPR_WCORNER_SW", "SPR_ROAD_LADDER", "SPR_YLINE_TOP",
                            "SPR_YLINE_V2", "SPR_ASPHALT3"],
                  "foes": ["SPR_CAR_BLACK", "SPR_CAR_BLUE", "SPR_MOTO_GREEN", "SPR_DRONE",
                           "SPR_SPIKERAT", "SPR_TRASHBAG", "SPR_CITYCAR_G", "SPR_CITYCAR_O",
                           "SPR_CARFRONT_S", "SPR_MOBSTER", "SPR_WHITESUIT", "SPR_CAPO",
                           "SPR_CITYCAR_G2", "SPR_CITYCAR_S2", "SPR_CITYCAR_O2",
                           "SPR_CITYBUS", "SPR_TRUCKTOP", "SPR_CARTOP", "SPR_VANTOP",
                           "SPR_RIGTOP", "SPR_LIMOTOP", "SPR_LADDERTOP",
                           "SPR_DUMPTRUCK", "SPR_FLATBED"],
                  "goods": ["SPR_COIN", "SPR_BLUEGEM", "SPR_KEY", "SPR_AMMO", "SPR_PISTOL",
                            "SPR_BOTTLE", "SPR_CANISTER"],
                  "avatars": ["SPR_GUNNER", "SPR_COMMANDO", "SPR_CAR_RED", "SPR_DETECTIVE"]},
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

# genre -> (map brief for the skin author, map rules for the implementer)
MAPS = {
 "catcher":    ("solid '#' ground on row 7 where the player runs; P on it; decor "
                "props along the side columns; rows 0-5 MUST stay open for falling items",
                "The map is your floor and dressing. The player runs on the row-7 "
                "ground; items fall through open columns. Do not add scenery in code."),
 "dodger":     ("2-4 small '#' obstacle clusters (2-4 cells) with wide gaps between, "
                "edges clear, P near centre, G spots spread into corners, light decor",
                "'#' cells are walls: block movement with mapSolid(x,y) checks. "
                "If the objective is collect, pickups appear at G spots (cycle "
                "mapX/mapY('G', i)). Hazards bounce off walls."),
 "racer":      ("decor only, NO '#': horizon props on rows 0-1, barrier/cone dressing "
                "on rows 6-7, P at left mid-row",
                "The map is background dressing; lanes and traffic stay procedural "
                "per the spec. Do not draw your own scenery."),
 "shooter":    ("P bottom-centre; optionally 1-2 '#' bunker cells on rows 5-6 as "
                "cover; decor in the top corners, S spots on row 0 for spawns",
                "Enemies enter at S spots when present. '#' bunkers block enemy "
                "descent and player bullets (mapSolid). Start the player at P."),
 "defender":   ("P at the exact centre cell (core position); a loose ring of decor "
                "near the edges; NO '#'",
                "The core sits at mapX('P',0), mapY('P',0). The map is dressing — "
                "draw nothing static yourself."),
 "sorter":     ("decor frame on edges; P marks the bins column on the left; NO '#'",
                "Bins anchor at the P column. Map is dressing only."),
 "stacker":    ("solid '#' ground across row 7; P marks the tower base column; "
                "decor at the far edges",
                "The tower rises from the ground row at mapX('P',0). Map is your "
                "floor; draw only the moving block and the tower in code."),
 "platformer": ("side view: row 7 ground with 1-2 gap pits, 2-3 floating '#' "
                "platform runs (3-5 cells) on different rows about 2 rows apart "
                "(jump reach), G spots ON platforms, S at the side edges, decor "
                "between platforms",
                "ALL ground/platforms come from the map: collide with "
                "mapSolid(x, y+8) for feet — do NOT generate rects. Goods live at "
                "G spots (cycle among them); enemies patrol from S spots. Falling "
                "into a pit (below the map) costs a life."),
 "breaker":    ("decor on the top corners; P marks the paddle column; NO '#' "
                "(bricks are game state, not map)",
                "Map is dressing; bricks/paddle/ball are yours per the spec."),
 "crosser":    ("row 7 = solid '#' start bank, row 0 = solid '#' goal bank, rows "
                "1-6 open lanes; 1-3 decor props ON the banks; P on the bottom bank",
                "The banks are the map's solid rows — standing on mapSolid cells "
                "is safe; hazards run only in the open rows between."),
 "snake":      ("a few interior '#' obstacle cells (3-8, small clusters), edges "
                "clear, P at centre-left, minimal decor",
                "'#' cells kill on contact exactly like walls and body — check "
                "mapSolid at the head. Food never spawns on solid cells."),
 "climber":    ("4-6 short '#' ledges (2-4 cells) spread across rows 1-7, P on the "
                "lowest ledge, sparse decor",
                "The map seeds the first screen of ledges (mapSolid); once the "
                "world scrolls, generate new platforms procedurally above."),
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


def roll(history, rng=None, force_genre=None, force_setting=None):
    """history: list of coords dicts (newest last). Returns coords.
    force_genre/force_setting: theme steering — explicit user intent, so it
    overrides anti-repeat and weights (still subject to DISABLED_GENRES)."""
    rng = rng or random.Random()

    pool_g = [g for g in GENRES if g not in DISABLED_GENRES]
    if force_genre in pool_g:
        genre = force_genre
    else:
        genres = _no_repeat(pool_g, [h.get("genre") for h in history[-4:]])
        genre = rng.choice(genres)
    G = GENRES[genre]

    pairs = [h.get("genre_objective") for h in history[-8:]]
    objs = ([o for o in G["objectives"] if f"{genre}/{o}" not in pairs]
            or list(G["objectives"]))
    objective = rng.choice(objs)

    threat = rng.choice(G["threats"])
    twist = rng.choice(_no_repeat(_fit_twists(genre), [h.get("twist") for h in history[-3:]]))
    pace = rng.choice(list(PACE))
    if force_setting in SETTINGS:
        setting = force_setting
    else:
        pool = _no_repeat(list(SETTINGS), [h.get("setting") for h in history[-3:]])
        w = SETTING_WEIGHTS.get(genre, {})
        setting = rng.choices(pool, weights=[w.get(s, 1) for s in pool])[0]
    kit = {k: (list(v) if isinstance(v, list) else v)
           for k, v in SETTINGS[setting].items()}
    avatar = rng.choice(kit.get("avatars", AVATARS))

    wild = None
    if rng.random() < WILD_P and not (history and history[-1].get("wild_kind")):
        kind = rng.choice(["guests", "swap", "blend", "mutator"])
        if kind == "guests":
            other = rng.choice([s for s in SETTINGS if s != setting])
            gs = (rng.sample(SETTINGS[other]["foes"], 2)
                  + rng.sample(SETTINGS[other]["goods"], 1))
            kit["foes"] = kit["foes"] + gs[:2]
            kit["goods"] = kit["goods"] + gs[2:]
            wild = {"kind": kind, "skin_line":
                    f"WILDCARD: outsiders from the {other} invade this {setting} — "
                    f"weave {gs} into the fiction as intruders."}
        elif kind == "swap":
            avatar = rng.choice(kit["foes"])
            wild = {"kind": kind, "skin_line":
                    "WILDCARD: the player IS the monster — the avatar is one of "
                    "the foes; explain why in-fiction."}
        elif kind == "blend":
            other = rng.choice([s for s in SETTINGS if s != setting])
            ok = SETTINGS[other]
            for role in ("props", "foes", "goods"):
                half = max(2, len(kit[role]) // 2)
                kit[role] = (rng.sample(kit[role], min(half, len(kit[role])))
                             + rng.sample(ok[role], min(half, len(ok[role]))))
            kit["accents"] = [kit["accents"][0], ok["accents"][1]]
            wild = {"kind": kind, "skin_line":
                    f"WILDCARD: this place is a fusion of {setting} and {other} — "
                    "invent and NAME the hybrid location."}
        else:
            mname, skinl, specl = rng.choice(MUTATORS)
            wild = {"kind": f"mutator:{mname}",
                    "skin_line": f"WILDCARD ({mname}): {skinl} — reflect it in "
                                 "title/blurb/entities.",
                    "spec_line": specl}

    p = {k: rng.randint(a, b) for k, (a, b) in G["params"].items()}
    mult = PACE[pace]
    for k in p:
        if k in ("period", "cool", "step0", "stepmin"):
            p[k] = max(1, round(p[k] * mult["period"]))
        elif k in ("pspeed", "speed", "scroll", "fall", "hspeed", "espeed",
                   "mspeed", "bspeed", "bounce"):
            p[k] = round(p[k] * mult["speed"])

    # mercy retune: soften hazards, never the player
    for k in ("fall", "hspeed", "espeed", "mspeed", "speed", "scroll"):
        if k in p:
            p[k] = round(p[k] * 0.88)
    if "ramp" in p:
        p["ramp"] = max(1, round(p["ramp"] * 0.8))
    if "slack" in p:
        p["slack"] += 1
    if pace == "frantic":                       # never stack worst cases
        if "ramp" in p and "ramp" in G["params"]:
            lo, hi = G["params"]["ramp"]
            p["ramp"] = min(p["ramp"], (lo + hi) // 2)
        if threat == "collision" and "slack" in p:
            p["slack"] += 1

    lo, hi = G["objectives"][objective]
    goal = round(rng.randint(lo, hi) * mult["goal"])
    goal = max(lo, min(goal, hi + 2))
    if goal > 12:                               # mercy: trim marathon goals
        goal = max(12, goal - 2)

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
    map_brief, map_use = MAPS[genre]
    spec += (f"\nLEVEL MAP: {map_use}"
             f"\nGoal: {verb} {goal} -> define GAME_GOAL {goal}, GAME_VERB \"{verb}\", "
             f"call eProgress as specified; the engine ends the game at the goal. "
             f"Set GAME_BG = {SETTINGS[setting]['bg'][0]} (engine fills the "
             f"background and draws the map — never fillScreen yourself)."
             "\nMERCY: define GAME_LIVES 10. Difficulty ramps STOP at +50% total. "
             "For the first 8 seconds (inp.t < 240) run hazard speeds at 85%.")
    if wild and wild.get("spec_line"):
        spec += "\nWILDCARD RULE (mandatory): " + wild["spec_line"]

    return {
        "genre": genre, "objective": objective, "genre_objective": f"{genre}/{objective}",
        "verb": verb, "goal": goal, "threat": threat, "twist": twist, "pace": pace,
        "setting": setting, "avatar": avatar, "params": p,
        "setting_kit": kit, "hint": G["hint"], "spec": spec,
        "map_brief": map_brief,
        "wild": (wild or {}).get("skin_line"),
        "wild_kind": (wild or {}).get("kind"),
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

    hist, seen, setg, wildc = [], collections.Counter(), collections.Counter(), collections.Counter()
    rng = random.Random(7)
    for i in range(400):
        c = roll(hist, rng)
        seen[c["genre"]] += 1
        if c["genre"] in ("racer", "crosser"):
            setg[c["setting"]] += 1
        assert c["objective"] in GENRES[c["genre"]]["objectives"], "bad pair"
        assert c["genre"] not in [h["genre"] for h in hist[-4:]], "genre repeat"
        assert "{" not in c["spec"], "unfilled spec placeholder"
        assert "GAME_LIVES 10" in c["spec"] and "STOP at +50%" in c["spec"], "mercy missing"
        if c["wild_kind"]:
            wildc[c["wild_kind"].split(":")[0]] += 1
            assert not (hist and hist[-1].get("wild_kind")), "two wild games in a row"
        for role in ("props", "foes", "goods"):
            miss = [s for s in c["setting_kit"][role] if s not in ids]
            assert not miss, f"rolled kit has unknown sprites: {miss}"
        assert c["avatar"] in ids, "unknown rolled avatar"
        if c["pace"] == "frantic" and "ramp" in c["params"] and "ramp" in GENRES[c["genre"]]["params"]:
            lo, hi = GENRES[c["genre"]]["params"]["ramp"]
            assert c["params"]["ramp"] <= (lo + hi) // 2, "frantic ramp not clamped"
        hist.append(c)
    total_wild = sum(wildc.values())
    print(f"genre distribution over 400 rolls: {dict(seen)}")
    print(f"wild games: {total_wild}/400 ({100*total_wild//400}%) by kind: {dict(wildc)}")
    assert 0.12 < total_wild / 400 < 0.32, "wild rate off target"
    print("racer/crosser settings:", dict(setg))
    print(json.dumps({k: v for k, v in roll(hist, rng).items()
                      if k not in ("spec", "setting_kit")}, indent=1))
    if "-v" in sys.argv:
        print(roll(hist, rng)["spec"])
