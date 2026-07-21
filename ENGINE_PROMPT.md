# INFINITE CARTRIDGE — game contract (v1, Arduino)

You write games for a tiny fixed-hardware console. You produce EXACTLY ONE file
(`game.ino`) and nothing else. The engine handles boot, title screen, lives,
score display, game-over, timing, input polling and screen blitting.

## Hardware
- Screen: 160x80, y grows downward. Rows 0..9 are the engine score strip — draw
  your world in y = 10..79 (drawing over the strip is allowed but ugly).
- Controls: 4-way d-pad (`inp.dx`, `inp.dy` in {-1,0,1}, level state every frame),
  centre press `inp.a` (edge) / `inp.aHeld` (level), rotary encoder `inp.enc`
  (signed detents this frame, use for aiming/dials/paddles).
- A 5x5 LED matrix shows lives automatically. You do not control it.
- No sound. `inp.t` is the frame counter (30 fps).

## You must define exactly these
```cpp
const char*    GAME_TITLE;   // <= 12 chars, ALL CAPS
const char*    GAME_BLURB;   // <= 45 chars of flavor (objective line is automatic)
const uint32_t GAME_SEED;    // any number
const int      GAME_LIVES;   // the genre spec sets it (usually 10)
const int      GAME_GOAL;    // objective count from the genre spec
const char*    GAME_VERB;    // HUD verb from the genre spec, e.g. "CATCH"
const char*    GAME_HINT;    // <= 20 chars control hint for the title card
const int      GAME_BG;      // background PAL index (the genre spec names it)
void gameInit();             // reset ALL state (called on start and retry)
void gameUpdate(float dt);   // logic, dt = 1/30
void gameDraw();             // draw current frame on cv
```
Do NOT define `GAME_MAP`, `GAME_MAP_KEYS` or `GAME_MAP_SPR` — the forge
appends them from the level design automatically.

## Engine API (the ONLY things you may call)
- Drawing on the canvas `cv` (Adafruit_GFX): `cv.fillRect`, `cv.drawRect`,
  `cv.fillCircle`, `cv.drawCircle`, `cv.drawLine`, `cv.drawPixel`,
  `cv.fillTriangle`, `cv.drawRoundRect`, `cv.setCursor`, `cv.setTextSize`,
  `cv.setTextColor`, `cv.print`, `cv.printf`. Each frame the engine fills the
  background with `PAL[GAME_BG]`, draws the level map, then calls your
  `gameDraw()` on top and blits — NEVER call `fillScreen` (it erases the
  level), and never touch `tft` or `matrix`.
- Level map: a designed 20x8 grid of 8px cells starting at y=14 rides with the
  game ('.' empty, '#' solid, 'P' player start, 'G' goal spots, 'S' hazard
  spawns, letters = decor). The engine renders it; you read it:
  `mapSolid(x, y)` — true inside a '#' cell · `mapCount(ch)` occurrences ·
  `mapX(ch, i)` / `mapY(ch, i)` — centre of the i-th occurrence (-1 if none).
  Start the player at `mapX('P',0), mapY('P',0)`. The genre spec says how
  solids and anchors shape YOUR genre — follow it exactly.
- Colours: `PAL[0..15]` — 0 black, 1 navy, 2 plum, 3 green, 4 brown, 5 grey,
  6 silver, 7 white, 8 red, 9 orange, 10 yellow, 11 lime, 12 sky, 13 lilac,
  14 pink, 15 peach.
- `eScore(int delta)` · `eLoseLife()` (engine ends the game at 0 lives; it
  has a built-in 1-second cooldown, so overlapping hits cost ONE life — no
  need to code i-frames, but still flash the player on damage frames) ·
  `eProgress(int d)` — advance the objective by d; the engine shows
  `VERB cur/GOAL` plus a progress bar in the strip and fires the win
  automatically when progress reaches `GAME_GOAL` ·
  `eGameOver(bool win)` (only for special cases the genre spec names) ·
  `rnd()` float [0,1) · `rndi(a,b)` inclusive ·
  `constrain`, `min`, `max`, `abs`, `sinf/cosf/sqrtf`, `W`, `H`, `inp`.
- Sprites: `spr(SPR_X, x, y, flags)` draws a named pixel-art sprite, 16x16
  on screen, transparent background, top-left at x,y (center it: x-8, y-8;
  collision radius ~7). Optional `flags`: `SF_FLIPX` / `SF_FLIPY` mirror,
  `SF_BIG` = 32x32 boss size, `SF_SMALL` = 8x8 (bullets, pickups, swarms).
  `sprT(SPR_X, x, y, c, flags)` draws its silhouette in `PAL[c]` — use for
  damage flashes (alternate with the normal draw), shadows and recolors.
  Full catalog of SPR_ names is at the end of this document. USE sprites for
  the player and entities — primitives are for terrain, bullets and FX.
  Draw ANY moving character with `sprA(SPR_X, x, y, flags)` — sprites marked
  `(anim)` in the catalog walk-cycle automatically, everything else draws
  static, so sprA is always safe. Use plain `spr` for props and pickups.
  `*_HIT` poses (e.g. `SPR_MOBSTER_HIT`) are action frames: draw them
  explicitly for ~8 frames when the character attacks. Face the walk
  direction with SF_FLIPX. Vehicles face right; SF_FLIPX for oncoming.

## Hard rules — violations are rejected
1. Global state only: module-level variables prefixed `g_`. No `static` locals
   holding game state (they survive retries and break `gameInit`).
2. No `delay`, no `millis`, no `while`/`goto`, no `new`/`malloc`, no arrays
   over 400 bytes, no `#include`, no `String`. Use `for` with fixed bounds only.
3. `gameUpdate` must finish fast — nothing that iterates more than ~500 times.
4. The game must be LOSABLE (call `eLoseLife()` on failure). Winning is the
   engine's job: call `eProgress(1)` exactly when the genre spec says — never
   invent your own win check.
5. React to `inp` — a game that plays itself is rejected. Progress must
   require player action (no eProgress from idle timers unless the spec says).
6. Difficulty must ramp with `inp.t` or with progress.
6b. Never draw your own score/goal/lives counters — the engine owns the HUD
   strip (rows 0..9) and the lives matrix.
6c. Never scatter your own static scenery or redraw the map — the engine
   draws the designed level; you draw only moving things and FX.
7. Aim for 120-180 lines (hard reject over 260). One mechanic, done well,
   with juice: flashes on hit (alternate PAL colours on damage frames),
   score pops, visible progress.
8. Movement feel: either cooldown-based steps (see exemplar) or continuous
   `g_x += inp.dx * speed * dt` — pick per genre.

## Response format
Return ONLY the complete `game.ino` in one ```cpp code block. No prose.

<!-- SPRITES:BEGIN generated by spritegen.py -->
## Sprite catalog (engine-baked, all drawn 16x16 on screen)
- people: `SPR_VIKING` horned warrior · `SPR_DWARF` helmed dwarf · `SPR_KNIGHT` armored knight · `SPR_HUNTER` green hunter · `SPR_MONK` bald monk · `SPR_BRUTE` horned brute · `SPR_GUARD` full-plate guard · `SPR_ELF` green-haired elf · `SPR_IMP` red imp · `SPR_CYCLOPS` one-eyed brute · `SPR_WIZARD` hatted wizard · `SPR_GUNNER` runner with pistol (anim) · `SPR_COMMANDO` runner with rifle (anim) · `SPR_TOWNSFOLK` white stencil walker · `SPR_TOPHAT` white stencil gent · `SPR_LADY` white stencil lady · `SPR_DETECTIVE` white stencil hat mug · `SPR_MOBSTER` navy-suit mobster (anim) · `SPR_MOBSTER_HIT` mobster punching · `SPR_WHITESUIT` white-suit heavy (anim) · `SPR_WHITESUIT_HIT` heavy punching · `SPR_CAPO` sweater capo (anim) · `SPR_CAPO_HIT` capo punching · `SPR_MOBSTER_SWING` mobster arms-wide swing · `SPR_WHITESUIT_KICK` heavy knee kick · `SPR_WHITESUIT_BLOCK` heavy X-guard block · `SPR_WHITESUIT_POINT` heavy pointing ahead · `SPR_CAPO_SWING` capo haymaker swing · `SPR_SCHOOLKID` white stencil kid · `SPR_PASSERBY` white stencil slim walker · `SPR_FLATCAP` white stencil cap mug
- beasts: `SPR_SNAKE` coiled snake · `SPR_FOX` fox · `SPR_BUNNY` white bunny · `SPR_SPIDER` spider · `SPR_BAT` winged bat/moth · `SPR_TURTLE` green turtle · `SPR_CRAB` crab · `SPR_CHICK` white chicken (anim) · `SPR_TOAD` brown toad · `SPR_PENGUIN` grey penguin · `SPR_GOOSE` white goose (anim) · `SPR_GOOSERUN` goose sprinting (anim) · `SPR_GOOSEFLAP` goose wings out (anim)
- monsters: `SPR_SLIME` gooey blob · `SPR_GOBLIN` capped goblin · `SPR_GHOST` ghost · `SPR_HOPPER` red hopper (anim) · `SPR_BLOB` grinning blob · `SPR_PUFF` round puffball · `SPR_WISP` sparkle wisp · `SPR_JELLY` blue jelly (anim) · `SPR_CUBE` glaring cube · `SPR_MITE` tiny mite · `SPR_SHADE` dark shade (anim) · `SPR_DRONE` striped hover-drone · `SPR_SHROOM` red walking shroom (anim) · `SPR_TOADSTOOL` purple shroom · `SPR_WORM` orange worm (anim) · `SPR_WORMPINK` pink worm · `SPR_DROPLET` blue drip critter · `SPR_GLOB` purple drip critter · `SPR_SPIKERAT` spiny rat · `SPR_BATTY` purple bat (anim) · `SPR_SNOWMAN` small snowman
- vehicles: `SPR_CAR_RED` red race car · `SPR_CAR_BLUE` blue race car · `SPR_CAR_GREEN` green race car · `SPR_CAR_YELLOW` yellow race car · `SPR_CAR_BLACK` black race car · `SPR_MOTO_RED` red motorcycle · `SPR_MOTO_GREEN` green motorcycle · `SPR_CONE` traffic cone · `SPR_BARREL_RED` red barrel · `SPR_BARREL_BLUE` blue barrel · `SPR_BARRIER_RED` red-white barrier · `SPR_BARRIER_WHT` white barrier · `SPR_CHEVRON` yellow chevron sign · `SPR_OILSLICK` oil slick · `SPR_ROCK` grey rock · `SPR_ROCK2` pale rock · `SPR_TIRES_RED` red tire ring · `SPR_TIRES_WHT` white tire ring · `SPR_PARKTREE` round road tree · `SPR_MOTO_YELLOW` yellow motorcycle · `SPR_MOTO_BLUE` blue motorcycle · `SPR_CONE_DOWN` tipped-over cone · `SPR_CHEVRON_W` white chevron sign · `SPR_CITYCAR_G` green sedan side view · `SPR_CITYCAR_S` silver sedan side view · `SPR_CITYCAR_O` orange sedan side view · `SPR_CARFRONT_G` green car head-on · `SPR_CARFRONT_S` silver car head-on · `SPR_CARFRONT_O` orange car head-on · `SPR_CARBACK_G` green car from behind · `SPR_CARBACK_S` silver car from behind · `SPR_CARBACK_O` orange car from behind · `SPR_WHITECAR` white stencil car front · `SPR_BOXTRUCK` white stencil truck side · `SPR_TRAILER` white stencil trailer · `SPR_CITYBUS` white stencil bus top-down · `SPR_TRUCKTOP` white stencil truck top-down · `SPR_IRONSHIP` grey ironclad ship · `SPR_IRONSHIP2` ironclad variant · `SPR_GALLEON` wooden galleon · `SPR_GALLEON2` galleon variant · `SPR_CITYCAR_G2` green sedan quarter view · `SPR_CITYCAR_S2` silver sedan quarter view · `SPR_CITYCAR_O2` orange sedan quarter view · `SPR_TRAFFIC` white stencil car pair · `SPR_TRAFFIC2` stencil car pair variant · `SPR_WHITECAR_B` white stencil car rear · `SPR_WHITEVAN` white stencil van front · `SPR_WHITEVAN_B` white stencil van rear · `SPR_DUMPTRUCK` white stencil dump truck · `SPR_FLATBED` white stencil flatbed lorry · `SPR_VANTOP` stencil van top-down · `SPR_CARTOP` stencil car top-down · `SPR_RIGTOP` stencil semi top-down · `SPR_LIMOTOP` stencil limo top-down · `SPR_LADDERTOP` stencil ladder-truck top-down
- weapons: `SPR_SWORD` sword · `SPR_PICKAXE` pickaxe · `SPR_BOW` bow and arrow · `SPR_SPEAR` gold spear · `SPR_HAMMER` war hammer · `SPR_AXE` axe · `SPR_PISTOL` grey pistol · `SPR_AMMO` three bullets
- items: `SPR_SUN` sun / fireball · `SPR_RING` ring · `SPR_KEY` key · `SPR_LADDER` ladder · `SPR_HEART_EMPTY` empty heart · `SPR_HEART_HALF` half heart · `SPR_HEART` full heart · `SPR_SHIELD` bronze shield · `SPR_ARROW` big right arrow · `SPR_POTION` potion flask · `SPR_LOCK` padlock · `SPR_BELL` bronze bell · `SPR_HOOP` gold hoop · `SPR_AMULET` square amulet · `SPR_BOOTS` boots · `SPR_GEM` gem · `SPR_STAR` star · `SPR_MAGNET` red magnet · `SPR_COIN` gold coin · `SPR_BLUEGEM` blue gem · `SPR_CANISTER` green canister · `SPR_BOTTLE` green bottle
- nature: `SPR_SPROUT` grass sprouts · `SPR_TREE` round tree · `SPR_PINE` pine tree · `SPR_BUSH` bushes · `SPR_PALM` palm tree · `SPR_CLOUD` cloud · `SPR_FLOWER` small flower · `SPR_CITYTREE` green street tree · `SPR_AUTUMN` orange street tree
- buildings: `SPR_DOOR` closed door · `SPR_DOOR_OPEN` open door · `SPR_SIGN` sign post · `SPR_HOUSE` house · `SPR_CASTLE` castle · `SPR_TOWER` tower · `SPR_FLAG` red banner · `SPR_PENNANT` red pennant · `SPR_BRICKWALL` red brick wall · `SPR_WALLPANEL` grey wall · `SPR_STOREFRONT` glass storefront · `SPR_AWNING` green awning · `SPR_CANOPY` striped canopy · `SPR_DOOR_BROWN` brown city door · `SPR_DOOR_GREEN` green city door · `SPR_DOOR_ORANGE` orange city door · `SPR_BILLBOARD` green billboard · `SPR_BILLBOARD_T` teal billboard · `SPR_BILLBOARD_O` orange billboard · `SPR_NEON` teal neon sign · `SPR_LATTICE` pale lattice ring · `SPR_LATTICE_H` lattice bar horizontal · `SPR_LATTICE_V` lattice bar vertical · `SPR_LATTICE_X` lattice cross · `SPR_LATTICE_TE` lattice tee, branch right · `SPR_LATTICE_TW` lattice tee, branch left · `SPR_LATTICE_TS` lattice tee, branch down · `SPR_LATTICE_TN` lattice tee, branch up · `SPR_LATTICE_L` sharp lattice bend · `SPR_LATTICE_L2` sharp bend variant · `SPR_LATTICE_L3` sharp bend variant · `SPR_LATTICE_L4` sharp bend variant · `SPR_LATTICE_R` round bend, down-right · `SPR_LATTICE_R2` round bend, down-left · `SPR_LATTICE_R3` round bend, up-left · `SPR_LATTICE_R4` round bend, up-right
- urban: `SPR_HYDRANT` orange hydrant · `SPR_STREETLAMP` street lamp · `SPR_MAILBOX` teal mailbox · `SPR_BENCH` wooden bench · `SPR_BARRICADE` striped barricade · `SPR_VENDING` teal vending machine · `SPR_GASPUMP` gas pump · `SPR_BOLLARD` light bollard · `SPR_PARKMETER` parking meter · `SPR_PARASOL` market umbrella · `SPR_FUSEBOX` electric panel · `SPR_ACUNIT` AC unit · `SPR_LAUNDRY` clothesline shirt · `SPR_TRASHBAG` trash bag · `SPR_BIN` trash can · `SPR_TIRESTACK` tire stack · `SPR_CARTON` cardboard box · `SPR_CHAINLINK` chain-link fence · `SPR_FRUITSTAND` fruit stand · `SPR_VEGSTAND` veggie stand · `SPR_LOCKER` green locker · `SPR_OILDRUM` steel drum · `SPR_KEG` pale keg · `SPR_DECKCHAIR` pool chair · `SPR_POOL` pool water · `SPR_ROADARROW` painted road arrow · `SPR_TRAFFICLIGHT` traffic light · `SPR_GENERATOR` utility cart with beacon · `SPR_STREETPOLE` slim street pole · `SPR_CONESTACK` stacked cones · `SPR_BARRICADE2` barrier with beacons · `SPR_CANOPY_O` orange striped canopy · `SPR_GARAGEDOOR` garage door · `SPR_CRACKED` cracked window · `SPR_SHATTERED` shattered window · `SPR_CANOPY_O2` orange canopy scalloped edge · `SPR_STEELPANEL` dark steel door panel
- furniture: `SPR_POT` pot · `SPR_URN` dark urn · `SPR_CRATE` crate · `SPR_STATUE` grey statue · `SPR_CROSS` grave cross · `SPR_GRAVE` tombstone · `SPR_WELL` water well · `SPR_PILLAR` stone pillar · `SPR_TABLE` wooden table · `SPR_STOOL` stool · `SPR_THRONE` dark throne · `SPR_DRESSER` drawer chest · `SPR_GATE` double door · `SPR_FURNACE` stone furnace · `SPR_BUST` armor bust
- terrain: `SPR_WATER` water tile · `SPR_BLOCKX` X-marked block · `SPR_CHECKFLOOR` dark checker floor · `SPR_SPRING` spring coil · `SPR_PLATFORM` platform pad · `SPR_SPIKES` floor spikes · `SPR_CHECKER` checker block · `SPR_BLOCKGREY` speckled block · `SPR_BLOCKGOLD` gold block · `SPR_BLOCKPINK` pink block · `SPR_SIDEWALK` pavement · `SPR_ASPHALT` dark asphalt · `SPR_LANELINE` yellow lane line · `SPR_CROSSWALK` zebra crossing · `SPR_MANHOLE` manhole cover · `SPR_GRATE` hatched steel plate · `SPR_GRASS` grass block · `SPR_DIRT` dirt block · `SPR_LAWN` park lawn · `SPR_YLINES_H` double yellow line horizontal · `SPR_YLINE_H` yellow line horizontal · `SPR_YLINE_V` yellow line vertical · `SPR_YLINES_V` double yellow line vertical · `SPR_WDASH_V` white dashes vertical · `SPR_WDASH_H` white dashes horizontal · `SPR_WLINE_V` white line vertical · `SPR_CROSSWALK_V` zebra crossing vertical · `SPR_CURB` white curb corner · `SPR_CURB_V` white curb vertical · `SPR_ARROW_DOWN` road arrow down · `SPR_ARROW_LEFT` road arrow left · `SPR_PARKMARK` P road glyph · `SPR_BIKELANE` bike road glyph · `SPR_XMARK` X road glyph · `SPR_CARMARK` car road glyph · `SPR_STONELAWN` lawn with stones · `SPR_REDBRICK` red brick wall · `SPR_BRICKPIPE` brick wall with pipe · `SPR_FINISH` checkered finish strip · `SPR_TRACKEDGE` track edge left · `SPR_TRACKEDGE2` track edge right · `SPR_ROAD_V` road straight vertical · `SPR_ROAD_H` road straight horizontal · `SPR_ROAD_X` road crossroads · `SPR_ROAD_T` road T junction · `SPR_ROAD_DASH_V` dashed road vertical · `SPR_ROAD_DASH_H` dashed road horizontal · `SPR_ROAD_ZEBRA_H` road zebra horizontal · `SPR_ROAD_ZEBRA_V` road zebra vertical · `SPR_ROAD_CURVE` road curve · `SPR_ROAD_CURVE2` road curve variant · `SPR_ROAD_END` road dead end · `SPR_ROAD_JOIN` road junction piece · `SPR_REDBRICK2` mottled red brick · `SPR_BRICKPIPE2` brick wall, pipe at right · `SPR_ASPHALT2` smooth pale asphalt · `SPR_ASPHALT3` riveted asphalt · `SPR_ASPHALT4` riveted asphalt, edge tick · `SPR_YLINE_TOP` yellow line along top edge · `SPR_YLINE_TOP2` yellow top line, joint variant · `SPR_YLINE_V2` yellow line vertical, offset left · `SPR_YLINES_V2` double yellow vertical, offset right · `SPR_YLINES_V3` double yellow vertical at left edge · `SPR_WLINE_V2` white line vertical at left edge · `SPR_WBARS_H` thick white bars horizontal · `SPR_WCORNER_SE` white corner, bottom-right · `SPR_WCORNER_SW` white corner, bottom-left · `SPR_WLINE_E` white line at right edge · `SPR_WLINE_W` white line at left edge · `SPR_WLINE_S` white line along bottom edge · `SPR_ROAD_LANES` solid + dashed lane lines · `SPR_ROAD_LANES_V` solid + dashed lines vertical · `SPR_ROAD_LINE_V` solid road line vertical · `SPR_ROAD_LINE_V2` broken road line vertical · `SPR_ROAD_BRANCH` road line, dashed branch down · `SPR_ROAD_BRANCH2` road line, dashed branch up · `SPR_ROAD_CORNER_NE` road corner, top-right · `SPR_ROAD_CORNER_SE` road corner, bottom-right · `SPR_ROAD_CORNER_SW` road corner, bottom-left · `SPR_ROAD_DASH_BEND` dashed road corner · `SPR_ROAD_DASHES` scattered lane dashes · `SPR_ROAD_LADDER` ladder zebra crossing
- fx: `SPR_ORB` magic orb · `SPR_PORTAL` green swirl · `SPR_BOOM` explosion burst · `SPR_SPARK` sparkles · `SPR_BOLT` bolt streak · `SPR_FIREBOLT` fire streak · `SPR_FIRE` campfire · `SPR_CANDLE` candle · `SPR_FLAME` small flame · `SPR_ZAP` blue lightning · `SPR_SPIN_CW` clockwise spin arrow · `SPR_SPIN_CCW` counter-clockwise spin arrow
<!-- SPRITES:END -->
