// PITLANE DASH — a real forged cartridge, kept as an exemplar.
// Demonstrates: map-driven platforming (mapSolid feet + bounded snap, no
// while), gravity, A-button jump, drifting goal (movegoal twist), named
// mercy()/ramp() helpers, patrol edge-turns, landing squash juice.
// Imitate this depth.

const char*    GAME_TITLE = "PITLANE DASH";
const char*    GAME_BLURB = "Race the circuit, snag drifting trophies!";
const uint32_t GAME_SEED  = 9271;
const int      GAME_LIVES = 10;
const int      GAME_GOAL  = 8;
const char*    GAME_VERB  = "CATCH";
const char*    GAME_HINT  = "DPAD: RUN  A: JUMP";
const int      GAME_BG    = 0;

// player
float g_px, g_py, g_pvx, g_pvy;
bool  g_grounded, g_wasGround;
int   g_squash;
int   g_face;

// trophy (drifting goal)
float g_gx, g_gy, g_gvx;
int   g_gspot;

// 2 patrol enemies
float g_ex[2], g_ey[2], g_evx[2];

// oil slick hazard
float g_ox, g_oy;

// cone drifter
float g_conex, g_coney;

static float mercy() { return inp.t < 240 ? 0.85f : 1.0f; }
static float ramp()  { float r = 1.0f + (float)(inp.t / 1800) * 0.5f; return r > 1.5f ? 1.5f : r; }

static void placeGoal() {
  int n = mapCount('G');
  if (n < 1) { g_gx = 80; g_gy = 62; return; }
  int idx = (g_gspot + 1 + rndi(0, n > 1 ? n - 2 : 0)) % n;
  g_gspot = idx;
  g_gx = mapX('G', idx);
  g_gy = mapY('G', idx) - 8;
  g_gvx = (rnd() > 0.5f ? 1.0f : -1.0f) * 19.2f;
}

static bool solidFeet(float x, float y) {
  return mapSolid(x - 5, y + 8) || mapSolid(x + 5, y + 8);
}

void gameInit() {
  g_px = mapX('P', 0); if (g_px < 0) g_px = 20;
  g_py = mapY('P', 0); if (g_py < 0) g_py = 62;
  g_pvx = 0; g_pvy = 0;
  g_grounded = false; g_wasGround = false;
  g_squash = 0; g_face = 0; g_gspot = -1;
  placeGoal();

  for (int i = 0; i < 2; i++) {
    float sx = mapX('S', i), sy = mapY('S', i);
    if (sx < 0) { sx = 20 + i * 100; sy = 22; }
    g_ex[i] = sx; g_ey[i] = sy;
    g_evx[i] = (i == 0 ? 1.0f : -1.0f) * 13.0f;
  }

  g_ox = 60; g_oy = 70;
  g_conex = W - 12; g_coney = g_oy;
}

void gameUpdate(float dt) {
  float spd = 48.0f;

  g_pvx = inp.dx * spd;
  if (inp.dx > 0) g_face = 0;
  if (inp.dx < 0) g_face = 1;

  if (inp.a && g_grounded) g_pvy = -173.0f;

  g_pvy += 406.0f * dt;

  float nx = g_px + g_pvx * dt;
  nx = constrain(nx, 8, W - 8);
  if (!mapSolid(nx, g_py) && !mapSolid(nx, g_py + 7))
    g_px = nx;

  float ny = g_py + g_pvy * dt;
  g_wasGround = g_grounded;
  g_grounded = false;

  if (g_pvy >= 0) {
    if (solidFeet(g_px, ny)) {
      // snap to surface without while: step back by velocity overshoot
      float step = g_pvy * dt;
      if (step < 1.0f) step = 1.0f;
      ny = g_py + step;
      for (int s = 0; s < 16; s++) {
        if (!solidFeet(g_px, ny - 1.0f)) break;
        ny -= 1.0f;
      }
      g_py = ny;
      g_pvy = 0;
      g_grounded = true;
    } else {
      g_py = ny;
    }
  } else {
    if (mapSolid(g_px, ny - 8)) {
      g_pvy = 0;
    } else {
      g_py = ny;
    }
  }

  if (g_grounded && !g_wasGround) g_squash = 4;
  if (g_squash > 0) g_squash--;

  if (g_py > H + 10) {
    eLoseLife();
    g_px = mapX('P', 0); if (g_px < 0) g_px = 20;
    g_py = 22; g_pvy = 0;
  }

  float gs = 19.2f * mercy() * ramp();
  g_gvx = (g_gvx > 0 ? gs : -gs);
  g_gx += g_gvx * dt;
  if (g_gx < 8)     { g_gx = 8;     g_gvx =  gs; }
  if (g_gx > W - 8) { g_gx = W - 8; g_gvx = -gs; }

  float tdx = g_px - g_gx, tdy = g_py - g_gy;
  if (tdx*tdx + tdy*tdy < 12*12) {
    eProgress(1); eScore(10);
    placeGoal();
  }

  float espd = 13.0f * mercy() * ramp();
  for (int i = 0; i < 2; i++) {
    g_ex[i] += g_evx[i] * dt * (espd / 13.0f);
    if (!solidFeet(g_ex[i] + g_evx[i] * 0.5f, g_ey[i]) ||
        g_ex[i] < 8 || g_ex[i] > W - 8)
      g_evx[i] = -g_evx[i];
    float edx = g_px - g_ex[i], edy = g_py - g_ey[i];
    if (edx*edx + edy*edy < 11*11) eLoseLife();
  }

  float odx = g_px - g_ox, ody = g_py - g_oy;
  if (odx*odx + ody*ody < 10*10) eLoseLife();

  float cspd = 18.0f * mercy();
  g_conex -= cspd * dt;
  if (g_conex < -8) g_conex = W + 8;
  float cdx = g_px - g_conex, cdy = g_py - g_coney;
  if (cdx*cdx + cdy*cdy < 10*10) eLoseLife();
}

void gameDraw() {
  spr(SPR_PENNANT, (int)g_gx - 8, (int)g_gy - 8);

  spr(SPR_CAR_BLUE,   (int)g_ex[0] - 8, (int)g_ey[0] - 8,
      g_evx[0] < 0 ? SF_FLIPX : 0);
  spr(SPR_MOTO_GREEN, (int)g_ex[1] - 8, (int)g_ey[1] - 8,
      g_evx[1] < 0 ? SF_FLIPX : 0);

  spr(SPR_OILSLICK,  (int)g_ox - 8,    (int)g_oy - 8);
  spr(SPR_CONE_DOWN, (int)g_conex - 8, (int)g_coney - 8);

  if (g_squash > 0)
    cv.fillRect((int)g_px - 8, (int)g_py + 6, 16, 3, PAL[9]);

  sprA(SPR_MOTO_RED, (int)g_px - 8, (int)g_py - 8,
       g_face ? SF_FLIPX : 0);
}
