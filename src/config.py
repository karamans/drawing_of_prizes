import os
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "my_bot")
SOURCE_CHAT = os.getenv("SOURCE_CHAT", "@trustat")
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL_ID")
KEYWORDS = os.getenv("KEYWORDS", "").split(",")
LEAVE_DELAY = int(os.getenv("LEAVE_DELAY", 3600))

# Validation
if not API_ID or not API_HASH:
    raise ValueError("API_ID and API_HASH must be set in .env")

try:
    API_ID = int(API_ID)
except ValueError:
    raise ValueError("API_ID must be an integer")


