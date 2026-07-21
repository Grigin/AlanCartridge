#pragma once
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <Adafruit_NeoPixel.h>

// Controls
#define TFT_CS     P2_IO0
#define TFT_RST    P2_IO1
#define TFT_DC     P2_IO2
#define MATRIX_PIN P4_IO1
#define DPAD_PIN   P1_IO0

// Encoder — AX22 ports carry 1 analog (IO0) + 2 digital (IO1/IO2);
// quadrature A/B on the digital pair, push on IO0. Comment out to disable.
#define ENC_A      P3_IO1
#define ENC_B      P3_IO2
// #define ENC_SW  P3_IO0   // enable after A/B verified

// Screen + framebuffer
static const int W = 160, H = 80;
SPIClass fspi(FSPI);
Adafruit_ST7735 tft = Adafruit_ST7735(&fspi, TFT_CS, TFT_DC, TFT_RST);
GFXcanvas16 cv(W, H);            // 25.6 KB canvas — games draw ONLY on cv

// pico-8 palette in RGB565
static const uint16_t PAL[16] = {
  0x0000, 0x194A, 0x792A, 0x042A, 0xAA86, 0x5AA9, 0xC618, 0xFF9D,
  0xF809, 0xFD00, 0xFF64, 0x0726, 0x2D7F, 0x83B3, 0xFBB5, 0xFE75 };
// 0 BLACK 1 NAVY 2 PLUM 3 GREEN 4 BROWN 5 GREY 6 SILVER 7 WHITE
// 8 RED 9 ORANGE 10 YELLOW 11 LIME 12 SKY 13 LILAC 14 PINK 15 PEACH

// Sprites — 8x8 pixel art baked from assets/ (regenerate: python spritegen.py)
#include "sprites.h"
// Every sprite draws 16x16 on screen by default; SF_SMALL = 8x8, SF_BIG =
// 32x32. Ids below SPR16_BASE are 8x8 texels (scaled up); ids at/above it
// are native 16x16 texels (4x the detail, same footprint).
enum { SF_FLIPX = 1, SF_FLIPY = 2, SF_BIG = 4, SF_SMALL = 8 };
static void _sprBlit(int id, int x, int y, uint8_t flags, int tint) {
  if (id < 0 || id >= SPR_COUNT) return;
  bool b16 = id >= SPR16_BASE;
  const uint8_t* d = b16 ? SPR16_PX[id - SPR16_BASE] : SPR_PX[id];
  int n = b16 ? 16 : 8;                      // texel grid side
  int s = (flags & SF_SMALL) ? 1 : (flags & SF_BIG) ? 4 : 2;
  if (b16) s >>= 1;                          // native 16x16 draws at half scale
  for (int py = 0; py < n; py++) for (int px = 0; px < n; px++) {
    uint8_t v = d[(py * n + px) >> 1];
    v = (px & 1) ? (v & 0x0F) : (v >> 4);
    if (!v) continue;                        // nibble 0 = transparent
    uint16_t c = PAL[tint >= 0 ? tint : v];
    int dx = (flags & SF_FLIPX) ? n - 1 - px : px;
    int dy = (flags & SF_FLIPY) ? n - 1 - py : py;
    if (s == 0) {                            // 16-bank SF_SMALL: sample to 8x8
      if ((px | py) & 1) continue;
      cv.drawPixel(x + dx / 2, y + dy / 2, c);
    }
    else if (s == 1) cv.drawPixel(x + dx, y + dy, c);
    else             cv.fillRect(x + dx * s, y + dy * s, s, s, c);
  }
}
void spr(int id, int x, int y, uint8_t flags = 0)  { _sprBlit(id, x, y, flags, -1); }
void sprT(int id, int x, int y, uint8_t col, uint8_t flags = 0) { _sprBlit(id, x, y, flags, col & 15); }

// ── Level map: 20x8 cells of 8px starting at y=14, forged per game ──────────
// '.' empty · '#' solid · 'P' player start · 'G' goal spot · 'S' spawn spot ·
// legend letters = decor sprites (16x16, centered on the cell, may overlap).
// The map constants are appended to game.ino by the forge, never hand-written.
extern const char* GAME_MAP;         // 160 chars, row-major
extern const char* GAME_MAP_KEYS;    // legend letters
extern const int   GAME_MAP_SPR[];   // sprite id per legend letter
static const int MAPW = 20, MAPH = 8, MAPY = 14;

static char mapCell(int c, int r) {
  if (c < 0 || c >= MAPW || r < 0 || r >= MAPH) return '.';
  return GAME_MAP[r * MAPW + c];
}
bool mapSolid(float x, float y) {
  return mapCell((int)x >> 3, ((int)y - MAPY) >> 3) == '#';
}
int mapCount(char ch) {
  int n = 0;
  for (int i = 0; i < MAPW * MAPH; i++) if (GAME_MAP[i] == ch) n++;
  return n;
}
static int _mapNth(char ch, int idx) {
  for (int i = 0; i < MAPW * MAPH; i++)
    if (GAME_MAP[i] == ch && idx-- == 0) return i;
  return -1;
}
float mapX(char ch, int idx) { int i = _mapNth(ch, idx); return i < 0 ? -1 : (i % MAPW) * 8 + 4; }
float mapY(char ch, int idx) { int i = _mapNth(ch, idx); return i < 0 ? -1 : MAPY + (i / MAPW) * 8 + 4; }

static void mapDraw() {                       // under the game layer each frame
  int solidSpr = -1;
  for (const char* k = GAME_MAP_KEYS; *k; k++)
    if (*k == '#') solidSpr = GAME_MAP_SPR[k - GAME_MAP_KEYS];
  for (int r = 0; r < MAPH; r++) for (int c = 0; c < MAPW; c++) {
    char ch = mapCell(c, r);
    if (ch == '.' || ch == 'P' || ch == 'G' || ch == 'S') continue;
    int x = c * 8, y = MAPY + r * 8;
    if (ch == '#') {
      if (solidSpr >= 0) spr(solidSpr, x, y, SF_SMALL);
      else { cv.fillRect(x, y, 8, 8, PAL[5]); cv.drawFastHLine(x, y, 8, PAL[1]); }
      continue;
    }
    for (int i = 0; GAME_MAP_KEYS[i]; i++)
      if (GAME_MAP_KEYS[i] == ch) { spr(GAME_MAP_SPR[i], x - 4, y - 4); break; }
  }
}

// Input
struct Input {
  int8_t dx = 0, dy = 0;   // normalized d-pad, -1/0/1 (level, every frame)
  bool a = false;          // centre-press EDGE (one frame)
  bool aHeld = false;      // centre-press level
  bool b = false, bHeld = false;   // encoder push (if ENC_SW defined)
  int8_t enc = 0;          // encoder detents this frame, signed
  uint32_t t = 0;          // frame counter (30 fps)
};
Input inp;

void sprA(int id, int x, int y, uint8_t flags = 0) {  // animated: auto walk-cycle
  if (id >= 0 && id < SPR_COUNT && ((inp.t >> 3) & 1)) id = SPR_ALT[id];
  spr(id, x, y, flags);
}

// D-pad resistor ladder: bands ~0 / ~760 / ~1555 / ~2333(centre) / ~3170 / 4095
// PADMAP — the ONE place to fix orientation. Defaults = decoded from your
// working sketch's on-screen behaviour. 60s calibration: run, press each
// direction, swap entries until it feels right.
struct PadDir { int8_t dx, dy; bool a; };
static const PadDir PADMAP[5] = {
  { 0,-1,false},   // band 0 (ADC ~0)     -> UP
  { 1, 0,false},   // band 1 (ADC ~760)   -> RIGHT
  {-1, 0,false},   // band 2 (ADC ~1555)  -> LEFT
  { 0, 0,true },   // band 3 (ADC ~2333)  -> A (centre press!)
  { 0, 1,false},   // band 4 (ADC ~3170)  -> DOWN
};

static int padBand() {
  int v = 0; for (int i = 0; i < 4; i++) v += analogRead(DPAD_PIN); v >>= 2;
  if (v < 200)  return 0;
  if (v < 1100) return 1;
  if (v < 1900) return 2;
  if (v < 2700) return 3;
  if (v < 3700) return 4;
  return -1;                               // released
}

// Encoder (quadrature, ISR)
#ifdef ENC_A
volatile int32_t encCount = 0;
void IRAM_ATTR encISR() {
  static uint8_t prev = 0;
  static const int8_t T[16] = {0,-1,1,0, 1,0,0,-1, -1,0,0,1, 0,1,-1,0};
  uint8_t s = (digitalRead(ENC_A) << 1) | digitalRead(ENC_B);
  encCount += T[(prev << 2) | s];
  prev = s;
}
#endif

// 5x5 matrix HUD
Adafruit_NeoPixel matrix(25, MATRIX_PIN, NEO_GRB + NEO_KHZ800);
static int serp(int r, int c) {              // logical row 0 = top → strip index
  int rr = 4 - r;
  return (rr % 2 == 0) ? (rr * 5 + c) : (rr * 5 + (4 - c));
}
static const uint8_t DIG[10][5] = {          // rows as 5-bit masks, bit4 = col0
  {0x0E,0x0A,0x0A,0x0A,0x0E},{0x04,0x0C,0x04,0x04,0x0E},
  {0x0E,0x02,0x0E,0x08,0x0E},{0x0E,0x02,0x0E,0x02,0x0E},
  {0x0A,0x0A,0x0E,0x02,0x08},  // 4: bottom row 0x08 is DELIBERATE for this
                               // LED matrix — do not "correct" it
  {0x0E,0x08,0x0E,0x02,0x0E},
  {0x0E,0x08,0x0E,0x0A,0x0E},{0x0E,0x02,0x04,0x04,0x04},
  {0x0E,0x0A,0x0E,0x0A,0x0E},{0x0E,0x0A,0x0E,0x02,0x0E}};
static const uint8_t DIG10[5] =              // "10": 1 + closed ring 0, stored
  {0x1D,0x15,0x15,0x15,0x1D};                // pre-mirrored (panel flips columns)
void mxDigit(int n, uint32_t col) {
  matrix.clear();
  if (n >= 0) {
    const uint8_t* g = (n == 10) ? DIG10 : DIG[n % 10];
    for (int r = 0; r < 5; r++) for (int c = 0; c < 5; c++)
      if (g[r] & (1 << (4 - c))) matrix.setPixelColor(serp(r, c), col);
  }
  matrix.show();
}
void mxPips(int n, uint32_t col) {           // 0..25 lit; strip order snakes bottom-up
  matrix.clear();
  for (int i = 0; i < n && i < 25; i++) matrix.setPixelColor(i, col);
  matrix.show();
}
uint32_t livesColor(int lives, int maxL) {
  if (lives * 3 >= maxL * 2) return matrix.Color(0, 180, 0);
  if (lives * 3 >= maxL)     return matrix.Color(180, 180, 0);
  return matrix.Color(180, 0, 0);
}

// Game contract (defined in game.ino)
extern const char* GAME_TITLE;
extern const char* GAME_BLURB;
extern const uint32_t GAME_SEED;
extern const int GAME_LIVES;                 // starting lives (1..9)
extern const int GAME_GOAL;                  // objective count; engine wins at it
extern const char* GAME_VERB;                // HUD verb, e.g. "CATCH"
extern const char* GAME_HINT;                // title-card control hint, <= 20 chars
extern const int GAME_BG;                    // background PAL index (engine fills it)
void gameInit();                             // reset game state
void gameUpdate(float dt);                   // logic @30fps; dt = 1/30
void gameDraw();                             // draw world on cv (engine clears+blits)

// Engine services for games
long  score_ = 0;  int lives_ = 3;  int progress_ = 0;
int32_t hitAt_ = -1000;                       // last eLoseLife frame (cooldown)
enum ShellState { TITLE, BRIEF, PLAY, OVER, BLANK };
ShellState shell = BLANK;  bool lastWin = false;
uint32_t stateAt = 0;

float rnd()              { return (float)random(0, 1 << 16) / (1 << 16); }
int   rndi(int a, int b) { return random(a, b + 1); }          // inclusive
void  eScore(int d) { score_ += d; }
void  eLoseLife();                            // forward decl
void  eGameOver(bool win);
void  eProgress(int d);                       // goal progress; auto-win at GAME_GOAL
void  sfx(const char*) {}                     // no buzzer wired — free port upgrade later

// Shell internals
static void showLives() { mxDigit(lives_, livesColor(lives_, GAME_LIVES)); }

void eGameOver(bool win) {
  if (shell != PLAY) return;
  lastWin = win; shell = OVER; stateAt = millis();
  cv.fillScreen(PAL[0]);
  cv.setTextSize(2); cv.setTextColor(win ? PAL[11] : PAL[8]);
  cv.setCursor(win ? 32 : 20, 20); cv.print(win ? "YOU WIN" : "GAME OVER");
  cv.setTextSize(1); cv.setTextColor(PAL[7]);
  cv.setCursor(40, 50); cv.printf("SCORE %ld", score_);
  tft.drawRGBBitmap(0, 0, cv.getBuffer(), W, H);
  mxDigit(win ? 9 : 0, win ? matrix.Color(0,180,0) : matrix.Color(180,0,0));
  Serial.printf("{\"ev\":\"over\",\"win\":%s,\"score\":%ld,\"title\":\"%s\"}\n",
                win ? "true" : "false", score_, GAME_TITLE);
}
void eLoseLife() {
  if (shell != PLAY) return;
  if ((int32_t)inp.t - hitAt_ < 30) return;   // 1s mercy cooldown: no multi-hits
  hitAt_ = inp.t;
  lives_--; showLives();
  Serial.printf("{\"ev\":\"life\",\"left\":%d}\n", lives_);
  if (lives_ <= 0) eGameOver(false);
}
void eProgress(int d) {
  if (shell != PLAY) return;
  progress_ += d;
  if (progress_ < 0) progress_ = 0;
  if (progress_ >= GAME_GOAL) { progress_ = GAME_GOAL; eGameOver(true); }
}

static void centerPrint(const char* s, int y, uint8_t size, uint16_t col) {
  int x = (W - 6 * size * (int)strlen(s)) / 2;
  cv.setTextSize(size); cv.setTextColor(col);
  cv.setCursor(x < 2 ? 2 : x, y); cv.print(s);
}

static void enterTitle() {
  shell = TITLE; stateAt = millis();
  score_ = 0; lives_ = GAME_LIVES; progress_ = 0;
  // grey cartridge with a paper label
  cv.fillScreen(PAL[0]);
  cv.fillRoundRect(1, 1, 158, 78, 5, PAL[5]);
  cv.drawRoundRect(1, 1, 158, 78, 5, PAL[0]);
  cv.drawFastHLine(6, 3, 148, PAL[6]);            // top sheen
  for (int gy = 7; gy <= 15; gy += 4) {           // grip ridges
    cv.drawFastHLine(10, gy, 140, PAL[1]);
    cv.drawFastHLine(10, gy + 1, 140, PAL[6]);
  }
  cv.fillRoundRect(6, 19, 148, 48, 2, PAL[7]);    // paper label
  cv.drawRoundRect(6, 19, 148, 48, 2, PAL[5]);
  uint8_t sh = 0;                                 // accent stripe: colour keyed
  for (const char* p = GAME_TITLE; *p; p++)       // to the title, so each game
    sh = sh * 31 + *p;                            // gets its own label livery
  static const uint8_t STRIPE_C[] = {8, 9, 11, 12, 14, 13, 2, 3};
  cv.fillRect(8, 21, 144, 3, PAL[STRIPE_C[sh % sizeof(STRIPE_C)]]);
  if (6 * 2 * (int)strlen(GAME_TITLE) <= 148)     // auto-fit: any length, one line
    centerPrint(GAME_TITLE, 26, 2, PAL[0]);
  else
    centerPrint(GAME_TITLE, 29, 1, PAL[0]);
  // blurb: one line up to 24 chars, else word-wrap onto two label lines
  int blen = strlen(GAME_BLURB);
  if (blen <= 24) centerPrint(GAME_BLURB, 48, 1, PAL[5]);
  else {
    int cut = 24;
    for (int i = 24; i > 10; i--) if (GAME_BLURB[i] == ' ') { cut = i; break; }
    char l1[26], l2[26];
    snprintf(l1, sizeof(l1), "%.*s", cut, GAME_BLURB);
    snprintf(l2, sizeof(l2), "%.24s", GAME_BLURB + cut + (GAME_BLURB[cut] == ' ' ? 1 : 0));
    centerPrint(l1, 45, 1, PAL[5]);
    centerPrint(l2, 53, 1, PAL[5]);
  }
  centerPrint("CENTRE to start", 70, 1, PAL[7]);
  tft.drawRGBBitmap(0, 0, cv.getBuffer(), W, H);
  mxPips(25, matrix.Color(40, 40, 120));
  Serial.printf("{\"ev\":\"title\",\"title\":\"%s\"}\n", GAME_TITLE);
}
static void enterPlay() {
  randomSeed(GAME_SEED);
  score_ = 0; lives_ = GAME_LIVES; progress_ = 0; inp.t = 0; hitAt_ = -1000;
  gameInit(); showLives();
  shell = PLAY; stateAt = millis();
  Serial.println("{\"ev\":\"play\"}");
}

// Boot gate: the cartridge "evaporates" on powerdown — the console comes up
// as an empty slot and only a bless from the forge (any serial host) revives
// it. Untethered power-ups stay blank; flash is untouched, so revival is
// instant once the pipeline reattaches.
static void drawBlank(bool showText) {
  cv.fillScreen(PAL[0]);
  cv.drawRoundRect(30, 14, 100, 52, 4, PAL[5]);   // empty cartridge slot
  cv.drawRoundRect(34, 18, 92, 44, 3, PAL[1]);
  for (int gy = 26; gy <= 38; gy += 6)            // ghost grip ridges
    cv.drawFastHLine(42, gy, 76, PAL[1]);
  if (showText) centerPrint("INSERT CARTRIDGE", 48, 1, PAL[6]);
  tft.drawRGBBitmap(0, 0, cv.getBuffer(), W, H);
}
static void enterBlank() {
  shell = BLANK; stateAt = millis();
  drawBlank(true);
  matrix.clear(); matrix.show();                  // no lives on an empty slot
}

// Pre-round briefing: controls steady 2s, blinking 1s, then play
static void enterBrief() { shell = BRIEF; stateAt = millis(); }
static void drawBrief(bool showHint) {
  cv.fillScreen(PAL[1]);
  centerPrint(GAME_TITLE, 12, 1, PAL[6]);
  char ob[24]; snprintf(ob, sizeof(ob), "%s %d", GAME_VERB, GAME_GOAL);
  centerPrint(ob, 28, 1, PAL[10]);
  if (showHint) centerPrint(GAME_HINT, 44, 1, PAL[7]);
  centerPrint("get ready...", 66, 1, PAL[5]);
  tft.drawRGBBitmap(0, 0, cv.getBuffer(), W, H);
}

static void pollInput() {
  static int stableBand = -1, cand = -2; static uint8_t candN = 0;
  static bool aPrev = false, bPrev = false;
  int band = padBand();
  if (band == cand) { if (candN < 2) candN++; } else { cand = band; candN = 0; }
  if (candN >= 2) stableBand = cand;          // 2-frame debounce
  inp.dx = inp.dy = 0; bool aNow = false;
  if (stableBand >= 0) { inp.dx = PADMAP[stableBand].dx; inp.dy = PADMAP[stableBand].dy;
                         aNow = PADMAP[stableBand].a; }
  inp.a = aNow && !aPrev; inp.aHeld = aNow; aPrev = aNow;
#ifdef ENC_A
  noInterrupts(); int32_t ec = encCount; encCount = 0; interrupts();
  inp.enc = (int8_t)constrain(ec / 4, -8, 8); // detents
#else
  inp.enc = 0;
#endif
#ifdef ENC_SW
  bool bNow = !digitalRead(ENC_SW);
  inp.b = bNow && !bPrev; inp.bHeld = bNow; bPrev = bNow;
#endif
}

static void pollSerial() {
  static char buf[32]; static uint8_t n = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || n >= sizeof(buf) - 1) {
      buf[n] = 0; n = 0;
      if (!strcmp(buf, "start")) { shell == BLANK ? enterTitle() : enterPlay(); }
      if (!strcmp(buf, "title")) enterTitle();
      if (!strcmp(buf, "bless") && shell == BLANK) enterTitle();
      if (!strcmp(buf, "ping")) {           // pong reports the current screen so
        static const char* SH[] = {"title", "brief", "play", "over", "blank"};
        Serial.printf("{\"ev\":\"pong\",\"shell\":\"%s\"}\n", SH[shell]);
      }                                     // the loop never flashes mid-game
      if (!strcmp(buf, "frame")) {          // mirror: @F <b64 of the framebuffer>
        static const char B64[] =
          "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        const uint8_t* fb = (const uint8_t*)cv.getBuffer();
        const uint32_t N = (uint32_t)W * H * 2;
        char out[512]; uint16_t o = 0;
        Serial.print("@F ");
        for (uint32_t i = 0; i < N; i += 3) {
          uint32_t v = (uint32_t)fb[i] << 16;
          if (i + 1 < N) v |= (uint32_t)fb[i + 1] << 8;
          if (i + 2 < N) v |= fb[i + 2];
          out[o++] = B64[(v >> 18) & 63];
          out[o++] = B64[(v >> 12) & 63];
          out[o++] = (i + 1 < N) ? B64[(v >> 6) & 63] : '=';
          out[o++] = (i + 2 < N) ? B64[v & 63] : '=';
          if (o >= 508) { Serial.write((const uint8_t*)out, o); o = 0; }
        }
        if (o) Serial.write((const uint8_t*)out, o);
        Serial.println();
      }
    } else if (c != '\r') buf[n++] = c;
  }
}

// ── Lifecycle — the primary .ino just calls these two ────────────────────────
void engineSetup() {
  fspi.begin(SCK, MISO, MOSI);   // panel first: swap the power-on snow for
  tft.initR(INITR_MINI160x80);   // clean black before the serial settle
  tft.invertDisplay(false);      // panel is TRUE-polarity: INVON negates every
                                 // frame (the white INSERT CARTRIDGE was this).
                                 // Judge against the GUI mirror, never memory —
                                 // the false-polarity "test" of 19 Jul was
                                 // never actually flashed, so nothing before
                                 // ~13:00 that day disproves this setting.
  tft.setRotation(3);
  tft.setSPISpeed(26000000);     // try 40000000 if stable
  tft.fillScreen(0);
  Serial.begin(115200);
  delay(300);
  matrix.begin(); matrix.setBrightness(20); matrix.show();
  pinMode(DPAD_PIN, INPUT);
#ifdef ENC_A
  pinMode(ENC_A, INPUT_PULLUP); pinMode(ENC_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ENC_A), encISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_B), encISR, CHANGE);
#endif
#ifdef ENC_SW
  pinMode(ENC_SW, INPUT_PULLUP);
#endif
  Serial.printf("{\"ev\":\"boot\",\"title\":\"%s\"}\n", GAME_TITLE);
  enterBlank();                  // empty slot until the forge blesses the boot
}

void engineLoop() {
  static uint32_t last = 0;
  pollSerial();
  uint32_t now = millis();
  if (now - last < 33) return;               // fixed ~30 fps
  last = now;
  pollInput();
  switch (shell) {
    case TITLE:
      if (inp.a) enterBrief();               // no autostart — centre only
      break;
    case BRIEF: {
      uint32_t el = now - stateAt;
      drawBrief(el < 2000 || ((el >> 7) & 1));   // 2s steady, 1s ~4Hz blink
      if (el >= 3000) enterPlay();
      break;
    }
    case PLAY:
      inp.t++;
      gameUpdate(1.0f / 30.0f);
      if (shell != PLAY) break;              // game ended inside update
      cv.fillScreen(PAL[GAME_BG & 15]);
      mapDraw();                             // level under the game layer
      gameDraw();
      cv.setTextSize(1); cv.setTextColor(PAL[6]);   // engine score strip
      cv.setCursor(2, 1); cv.printf("%ld", score_);
      cv.setTextColor(PAL[10]);                     // goal readout + bar
      cv.setCursor(82, 1); cv.printf("%s %d/%d", GAME_VERB, progress_, GAME_GOAL);
      cv.fillRect(82, 8, 76, 1, PAL[5]);
      if (GAME_GOAL > 0 && progress_ > 0)
        cv.fillRect(82, 8, 76 * progress_ / GAME_GOAL, 1, PAL[11]);
      tft.drawRGBBitmap(0, 0, cv.getBuffer(), W, H);
      break;
    case OVER:
      if (now - stateAt > 3000 && (inp.a || now - stateAt > 8000)) enterTitle();
      break;
    case BLANK: {                            // empty slot: buttons dead, wait
      drawBlank(!(((now - stateAt) / 700) & 1));
      static uint32_t hello = 0;
      if (now - hello > 2000) {              // re-announce for late hosts
        hello = now;
        Serial.println("{\"ev\":\"blank\"}");
      }
      break;
    }
  }
}
