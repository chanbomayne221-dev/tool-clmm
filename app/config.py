import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

ADMIN_IDS = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().lstrip("-").isdigit()
]

_src = os.getenv("SOURCE_CHAT_ID", "").strip()
SOURCE_CHAT_ID = int(_src) if _src.lstrip("-").isdigit() else None

DB_PATH = os.getenv("DB_PATH", "data/bot.db")

# Prediction tuning
MIN_CONFIDENCE = 0.52
MAX_CONFIDENCE = 0.78
HISTORY_WINDOW = 200
ML_MIN_SAMPLES = 30

# Anti spam
SEND_COOLDOWN_SECONDS = 2

TZ = "Asia/Ho_Chi_Minh"
