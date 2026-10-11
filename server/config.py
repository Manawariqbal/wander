"""Central config, loaded from environment / .env."""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default)


ELEVENLABS_API_KEY = _get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_MODEL = _get("ELEVENLABS_MODEL", "eleven_flash_v2_5")

OLLAMA_URL = _get("OLLAMA_URL", "http://localhost:11434")
GEMMA_MODEL = _get("GEMMA_MODEL", "gemma3:4b")

WHISPER_MODEL = _get("WHISPER_MODEL", "base.en")
WHISPER_DEVICE = _get("WHISPER_DEVICE", "auto")
WHISPER_COMPUTE = _get("WHISPER_COMPUTE", "int8")

ORS_API_KEY = _get("ORS_API_KEY")

PIPER_BIN = _get("PIPER_BIN", "piper")
PIPER_MODEL = _get("PIPER_MODEL")

DB_PATH = _get("DB_PATH", "data/wander.db")

# Walk behaviour
GEOFENCE_RADIUS_M = 40
NARRATION_COOLDOWN_S = 120
POI_SEARCH_RADIUS_M = 600
CHALLENGE_EVERY_S = 420      # a "touch grass" prompt roughly every 7 minutes
SUNSET_WARN_MIN = 45         # warn once when sunset is this close