import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


def get_env(key: str, default: Optional[str] = None, required: bool = True) -> str:
    value = os.getenv(key, default)
    if required and value is None:
        print(f"[ERROR] Variable de entorno requerida no encontrada: {key}")
        print(f"        Asegúrate de que exista en tu archivo .env")
        sys.exit(1)
    return value


SECRET_KEY = get_env("SECRET_KEY")
ANTHROPIC_API_KEY = get_env("ANTHROPIC_API_KEY")
OPENAI_API_KEY = get_env("OPENAI_API_KEY")
ADMIN_EMAIL = get_env("ADMIN_EMAIL")
ADMIN_PASSWORD = get_env("ADMIN_PASSWORD")
DATABASE_URL = get_env("DATABASE_URL", default="sqlite:///./freeagent.db", required=False)
ENV = get_env("ENV", default="development", required=False)
INSTAGRAM_USERNAME = get_env("INSTAGRAM_USERNAME", default=None, required=False)
INSTAGRAM_PASSWORD = get_env("INSTAGRAM_PASSWORD", default=None, required=False)
INSTAGRAM_SESSION_FILE = get_env("INSTAGRAM_SESSION_FILE", default="/var/www/freeagent/insta_session", required=False)
INSTAGRAM_COOKIES_FILE = get_env("INSTAGRAM_COOKIES_FILE", default="/var/www/freeagent/instagram_cookies.txt", required=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8
