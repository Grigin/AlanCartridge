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
  {0x0A,0x0A,0x0E,0x02,0x02},{0x0E,0x08,0x0E,0x02,0x0E},
  {0x0E,0x08,0x0E,0x0A,0x0E},{0x0E,0x02,0x04,0x04,0x04},
  {0x0E,0x0A,0x0E,0x0A,0x0E},{0x0E,0x0A,0x0E,0x02,0x0E}};
void mxDigit(int n, uint32_t col) {
  matrix.clear();
  if (n >= 0) { n %= 10;
    for (int r = 0; r < 5; r++) for (int c = 0; c < 5; c++)
      if (DIG[n][r] & (1 << (4 - c))) matrix.setPixelColor(serp(r, c), col);
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
void gameInit();                             // reset game state
void gameUpdate(float dt);                   // logic @30fps; dt = 1/30
void gameDraw();                             // draw world on cv (engine clears+blits)

// Engine services for games
long  score_ = 0;  int lives_ = 3;
enum ShellState { TITLE, PLAY, OVER };
ShellState shell = TITLE;  bool lastWin = false;
uint32_t stateAt = 0;

float rnd()              { return (float)random(0, 1 << 16) / (1 << 16); }
int   rndi(int a, int b) { return random(a, b + 1); }          // inclusive
void  eScore(int d) { score_ += d; }
void  eLoseLife();                            // forward decl
void  eGameOver(bool win);
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
  lives_--; showLives();
  Serial.printf("{\"ev\":\"life\",\"left\":%d}\n", lives_);
  if (lives_ <= 0) eGameOver(false);
}

static void enterTitle() {
  shell = TITLE; stateAt = millis();
  score_ = 0; lives_ = GAME_LIVES;
  cv.fillScreen(PAL[1]);
  cv.setTextSize(2); cv.setTextColor(PAL[10]);
  cv.setCursor(8, 14); cv.print(GAME_TITLE);
  cv.setTextSize(1); cv.setTextColor(PAL[6]);
  cv.setCursor(8, 44); cv.print(GAME_BLURB);
  cv.setCursor(8, 66); cv.setTextColor(PAL[7]); cv.print("press CENTRE to play");
  tft.drawRGBBitmap(0, 0, cv.getBuffer(), W, H);
  mxPips(25, matrix.Color(40, 40, 120));
  Serial.printf("{\"ev\":\"title\",\"title\":\"%s\"}\n", GAME_TITLE);
}
static void enterPlay() {
  randomSeed(GAME_SEED);
  score_ = 0; lives_ = GAME_LIVES; inp.t = 0;
  gameInit(); showLives();
  shell = PLAY; stateAt = millis();
  Serial.println("{\"ev\":\"play\"}");
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
      if (!strcmp(buf, "start")) enterPlay();
      if (!strcmp(buf, "title")) enterTitle();
      if (!strcmp(buf, "ping"))  Serial.println("{\"ev\":\"pong\"}");
    } else if (c != '\r') buf[n++] = c;
  }
}

// ── Lifecycle — the primary .ino just calls these two ────────────────────────
void engineSetup() {
  Serial.begin(115200);
  delay(300);
  fspi.begin(SCK, MISO, MOSI);
  tft.initR(INITR_MINI160x80);   // if colours/offset look wrong: INITR_MINI160x80_PLUGIN
  tft.invertDisplay(true);
  tft.setRotation(3);
  tft.setSPISpeed(26000000);     // try 40000000 if stable
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
  enterTitle();
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
      if (inp.a || now - stateAt > 6000) enterPlay();
      break;
    case PLAY:
      inp.t++;
      gameUpdate(1.0f / 30.0f);
      if (shell != PLAY) break;              // game ended inside update
      cv.fillScreen(PAL[0]);
      gameDraw();
      cv.setTextSize(1); cv.setTextColor(PAL[6]);   // engine score strip
      cv.setCursor(2, 1); cv.printf("%ld", score_);
      tft.drawRGBBitmap(0, 0, cv.getBuffer(), W, H);
      break;
    case OVER:
      if (now - stateAt > 3000 && (inp.a || now - stateAt > 8000)) enterTitle();
      break;
  }
}
