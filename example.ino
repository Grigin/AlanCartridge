// FOREST VIGIL — a real forged cartridge, kept as an exemplar.
// Demonstrates: entity array, encoder as primary control, survive-objective
// progress timer, the mercy contract done right (ramp capped at +50%, first
// 8 s at 85%), sprT damage flash, SF_BIG, milestone twist (shield shrinks).

const char*    GAME_TITLE = "FOREST VIGIL";
const char*    GAME_BLURB = "Guard the glade till dawn.";
const uint32_t GAME_SEED  = 7331;
const int      GAME_LIVES = 10;
const int      GAME_GOAL  = 44;
const char*    GAME_VERB  = "SURVIVE";
const char*    GAME_HINT  = "DIAL: SPIN SHIELD";
const int      GAME_BG    = 1;

const int MAXH = 10;

float g_cx, g_cy;
float g_ang;
float g_shieldR;
int   g_hurtFlash;
int   g_boomX, g_boomY, g_boomT;

float g_hx[MAXH], g_hy[MAXH], g_hvx[MAXH], g_hvy[MAXH];
bool  g_hon[MAXH];
int   g_spawnTimer;
float g_progTimer;
int   g_lastProg;

static float shieldRadius() {
  int p = g_lastProg;
  float r = 27.0f;
  if (p >= GAME_GOAL * 2 / 3) r *= 0.7f;
  else if (p >= GAME_GOAL / 3) r *= 0.85f;
  return r;
}

static void spawnHazard() {
  for (int i = 0; i < MAXH; i++) {
    if (g_hon[i]) continue;
    float a = rnd() * 6.2832f;
    float ex = g_cx + cosf(a) * 90.0f;
    float ey = g_cy + sinf(a) * 90.0f;
    ex = constrain(ex, 10.0f, (float)(W - 10));
    ey = constrain(ey, 14.0f, (float)(H - 6));
    g_hx[i] = ex; g_hy[i] = ey;
    float secs = inp.t / 30.0f;
    float ramp = 1.0f + (secs / 10.0f) * 0.10f;
    if (ramp > 1.50f) ramp = 1.50f;
    if (inp.t < 240) ramp *= 0.85f;
    float spd = 13.0f * ramp;
    float dx = g_cx - ex, dy = g_cy - ey;
    float d = sqrtf(dx * dx + dy * dy) + 0.001f;
    g_hvx[i] = dx / d * spd;
    g_hvy[i] = dy / d * spd;
    g_hon[i] = true;
    return;
  }
}

void gameInit() {
  g_cx = mapX('P', 0); g_cy = mapY('P', 0);
  g_ang = 0.0f;
  g_hurtFlash = 0;
  g_boomT = 0;
  g_spawnTimer = 48;
  g_progTimer = 0.0f;
  g_lastProg = 0;
  for (int i = 0; i < MAXH; i++) g_hon[i] = false;
}

void gameUpdate(float dt) {
  g_ang += inp.enc * 0.35f;
  if (inp.dx) g_ang += inp.dx * 2.5f * dt;

  g_shieldR = shieldRadius();
  float sx = g_cx + cosf(g_ang) * g_shieldR;
  float sy = g_cy + sinf(g_ang) * g_shieldR;

  if (--g_spawnTimer <= 0) {
    spawnHazard();
    float secs = inp.t / 30.0f;
    float ramp = 1.0f + (secs / 10.0f) * 0.10f;
    if (ramp > 1.50f) ramp = 1.50f;
    int period = (int)(48.0f / ramp);
    if (period < 20) period = 20;
    g_spawnTimer = period;
  }

  for (int i = 0; i < MAXH; i++) {
    if (!g_hon[i]) continue;
    g_hx[i] += g_hvx[i] * dt;
    g_hy[i] += g_hvy[i] * dt;

    float dsx = g_hx[i] - sx, dsy = g_hy[i] - sy;
    if (dsx * dsx + dsy * dsy < 10.0f * 10.0f) {
      g_boomX = (int)g_hx[i]; g_boomY = (int)g_hy[i]; g_boomT = 8;
      g_hon[i] = false;
      eScore(5);
      continue;
    }

    float dcx = g_hx[i] - g_cx, dcy = g_hy[i] - g_cy;
    if (dcx * dcx + dcy * dcy < 14.0f * 14.0f) {
      g_hon[i] = false;
      g_hurtFlash = 12;
      eLoseLife();
      continue;
    }

    if (g_hx[i] < 4 || g_hx[i] > W - 4 || g_hy[i] < 14 || g_hy[i] > H - 4) {
      g_hon[i] = false;
    }
  }

  g_progTimer += dt;
  if (g_progTimer >= 1.0f) {
    g_progTimer -= 1.0f;
    eProgress(1);
    g_lastProg++;
  }

  if (g_hurtFlash > 0) g_hurtFlash--;
  if (g_boomT > 0) g_boomT--;
}

void gameDraw() {
  float sx = g_cx + cosf(g_ang) * g_shieldR;
  float sy = g_cy + sinf(g_ang) * g_shieldR;

  cv.drawCircle((int)g_cx, (int)g_cy, (int)g_shieldR, PAL[3]);

  if (g_hurtFlash > 0 && (g_hurtFlash & 1))
    sprT(SPR_GUARD, (int)g_cx - 16, (int)g_cy - 16, 8, SF_BIG);
  else
    spr(SPR_GUARD, (int)g_cx - 16, (int)g_cy - 16, SF_BIG);

  cv.fillCircle((int)sx, (int)sy, 5, PAL[11]);
  cv.drawCircle((int)sx, (int)sy, 7, PAL[7]);

  for (int i = 0; i < MAXH; i++) {
    if (!g_hon[i]) continue;
    sprA(SPR_HOPPER, (int)g_hx[i] - 8, (int)g_hy[i] - 8);
  }

  if (g_boomT > 0)
    spr(SPR_BOOM, g_boomX - 8, g_boomY - 8);
}
