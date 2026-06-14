import os
from dotenv import load_dotenv

load_dotenv()

# Discord
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
ROLE_ID = int(os.getenv("ROLE_ID", "0"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # legacy, unused
RANKING_CHANNEL_ID = int(os.getenv("RANKING_CHANNEL_ID", "0"))
GUILD_NAME = os.getenv("GUILD_NAME", "Gildia")

# Projekt Hard
HARD_LOGIN = os.getenv("HARD_LOGIN")
HARD_PASSWORD = os.getenv("HARD_PASSWORD")
HARD_PIN = os.getenv("HARD_PIN")

# PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway auto-ustawia to

# Inne
LIMIT = int(os.getenv("LIMIT", "4"))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# Kolory
DARK_BG    = "1a1a2e"
GOLD       = "FFD700"
SILVER     = "C0C0C0"
BRONZE     = "CD7F32"
HEADER_BG  = "16213e"
ROW_EVEN   = "0f3460"
ROW_ODD    = "1a1a2e"
ZERO_COLOR = "888888"
WHITE      = "FFFFFF"
RED        = "FF4444"
ORANGE     = "FFA500"
GREEN      = "44FF88"
