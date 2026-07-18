// First generated game

const char*    GAME_TITLE = "STARFALL YARD";
const char*    GAME_BLURB = "Grab 8 stars. Walls bite.";
const uint32_t GAME_SEED  = 1337;
const int      GAME_LIVES = 3;

// module-level state, prefix g_
float g_x, g_y;
int   g_sx, g_sy;        // star position
int   g_got;
float g_cool;

static void placeStar() { g_sx = rndi(12, W - 12); g_sy = rndi(14, H - 12); }

void gameInit() {
  g_x = W / 2; g_y = H / 2;
  g_got = 0; g_cool = 0;
  placeStar();
}

void gameUpdate(float dt) {
  g_cool -= dt;
  if ((inp.dx || inp.dy) && g_cool <= 0) {
    g_x += inp.dx * 6; g_y += inp.dy * 6;
    g_cool = 0.12f;                       // move cadence like the original
  }
  // encoder nudges the star (chaos dial)
  if (inp.enc) g_sx = constrain(g_sx + inp.enc * 3, 8, W - 8);

  bool hitWall = false;
  if (g_x < 6)     { g_x = 6;     hitWall = true; }
  if (g_x > W - 6) { g_x = W - 6; hitWall = true; }
  if (g_y < 12)    { g_y = 12;    hitWall = true; }
  if (g_y > H - 6) { g_y = H - 6; hitWall = true; }
  if (hitWall) eLoseLife();

  float ddx = g_x - g_sx, ddy = g_y - g_sy;
  if (ddx * ddx + ddy * ddy < 8 * 8) {
    g_got++; eScore(10); placeStar();
    if (g_got >= 8) eGameOver(true);
  }
}

void gameDraw() {
  cv.drawRect(0, 10, W, H - 10, PAL[5]);            // arena
  cv.fillCircle(g_sx, g_sy, 3, PAL[10]);            // star
  cv.drawPixel(g_sx, g_sy - 5, PAL[10]);
  cv.fillCircle((int)g_x, (int)g_y, 4, PAL[7]);     // player
  cv.setTextColor(PAL[10]); cv.setCursor(W - 30, 1);
  cv.printf("%d/8", g_got);
}
