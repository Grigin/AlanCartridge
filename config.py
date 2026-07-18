import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
SKETCH = ROOT / "forge_sketch"
GAME_FILE = SKETCH / "game.ino"
LIB = ROOT / "library"

FQBN = os.environ.get("FORGE_FQBN", "esp32:esp32:axiometa_genesis_mini")
PORT_HINT = os.environ.get("FORGE_PORT", "/dev/cu.usbmodem1101")
MODEL = os.environ.get("FORGE_MODEL", "claude-sonnet-4-6")
BAUD = 115200

CONTRACT = (ROOT / "ENGINE_PROMPT.md").read_text()
GAME_EXAMPLES = sorted(ROOT.glob("example*.ino"))  # inserted into prompt
