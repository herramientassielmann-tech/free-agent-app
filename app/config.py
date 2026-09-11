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

# ── Avisos por email (Resend) ──────────────────────────────────────────────
# Todo opcional: sin RESEND_API_KEY la app funciona igual, simplemente no
# manda nada. Así el despliegue no depende de tener el DNS ya propagado.
RESEND_API_KEY = get_env("RESEND_API_KEY", default=None, required=False)
# El remitente debe ser un dominio verificado en Resend. Se usa un subdominio
# propio (avisos.) para no tocar el SPF de robertsielmann.com, que ya está en
# uso por Google Workspace: dos registros SPF en un dominio los invalidan.
EMAIL_FROM = get_env("EMAIL_FROM",
                     default="Free Agent Academy <tareas@avisos.robertsielmann.com>",
                     required=False)
# A dónde van las respuestas si un realtor contesta al aviso.
EMAIL_REPLY_TO = get_env("EMAIL_REPLY_TO", default=None, required=False)
APP_URL = get_env("APP_URL", default="https://tool.robertsielmann.com", required=False)

# ── Alta de alumnos (onboarding) ───────────────────────────────────────────
# Todo opcional: sin estas claves el circuito se puede recorrer igual, sólo que
# los botones correspondientes salen desactivados con un aviso. Así se puede
# desplegar y probar antes de tener las cuentas de Stripe y Skool listas.
STRIPE_PAYMENT_LINK = get_env("STRIPE_PAYMENT_LINK", default=None, required=False)
STRIPE_WEBHOOK_SECRET = get_env("STRIPE_WEBHOOK_SECRET", default=None, required=False)
SKOOL_INVITE_URL = get_env("SKOOL_INVITE_URL", default=None, required=False)
CALENDLY_ONBOARDING_URL = get_env("CALENDLY_ONBOARDING_URL", default=None, required=False)
CALENDLY_WEBHOOK_SECRET = get_env("CALENDLY_WEBHOOK_SECRET", default=None, required=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8
