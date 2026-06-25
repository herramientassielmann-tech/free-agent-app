# Free Agent Academy — Generador de Guiones

> Plataforma para *realtors* hispanohablantes. Pega un vídeo viral de YouTube, TikTok o Instagram y te devuelve un guión adaptado a tu perfil —con estructura Hook · Desarrollo · Conclusión— y un caption listo para publicar. Siempre en español.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Anthropic-D97757?logo=anthropic&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-4169E1?logo=postgresql&logoColor=white)
![Estado](https://img.shields.io/badge/estado-en%20producci%C3%B3n-success)

---

## La idea

Un realtor ve un vídeo que funciona y quiere su propia versión. En lugar de copiarlo, la app lo **transcribe, analiza su estructura y reescribe el guión** con la voz y el nicho del realtor. Entra inspiración ajena, sale contenido propio.

## Cómo funciona

```
Vídeo (YouTube / TikTok / Instagram)
   │
   ▼
1. Transcripción     app/services/transcription.py
      YouTube → youtube-transcript-api
      TikTok / IG → descarga audio (yt-dlp) → Whisper (OpenAI)
2. Generación        app/services/generator.py
      Claude reescribe con análisis estructural + perfil del realtor
3. Resultado         guión Hook–Desarrollo–Conclusión + caption, guardado en el historial
```

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI + Uvicorn |
| Plantillas | Jinja2 (`app/templates/`) |
| IA | Anthropic Claude (guiones) · OpenAI Whisper (transcripción) |
| Fuentes de vídeo | youtube-transcript-api · yt-dlp · instaloader |
| Base de datos | PostgreSQL/Supabase (prod) · SQLite (local) vía SQLAlchemy |
| Auth | JWT (python-jose) + passlib/bcrypt |

## Puesta en marcha local

**Requisitos:** Python 3.11+ y FFmpeg (lo necesita yt-dlp).

```bash
# FFmpeg
brew install ffmpeg            # macOS
# sudo apt install ffmpeg      # Linux

# Entorno
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-local.txt    # versiones pensadas para Mac/dev

# Configuración
cp .env.example .env          # rellena tus claves

# Arrancar
uvicorn app.main:app --reload --port 8000
```

Abre **http://localhost:8000**. El usuario admin se crea solo en el primer arranque a partir de `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

> Hay dos ficheros de dependencias a propósito: **`requirements-local.txt`** para desarrollo (incluye `instaloader`, yt-dlp reciente, SQLite) y **`requirements.txt`** para producción (PostgreSQL con `psycopg`).

## Variables de entorno

| Variable | Para qué |
|----------|----------|
| `SECRET_KEY` | Firma de los JWT — genera con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ANTHROPIC_API_KEY` | Claude, para generar los guiones |
| `OPENAI_API_KEY` | Whisper, para transcribir TikTok/Instagram |
| `ADMIN_EMAIL` · `ADMIN_PASSWORD` | Admin inicial (se crea al arrancar) |
| `DATABASE_URL` | PostgreSQL en prod; SQLite en local |
| `ENV` | `development` / `production` |

## Rutas

| Ruta | Qué es |
|------|--------|
| `/` | Dashboard — generador de guiones |
| `/login` | Autenticación |
| `/profile` | Perfil del realtor (nicho, tono, ciudad…) |
| `/history` | Guiones generados |
| `/admin` | Panel de administración (solo admins) |

## Estructura

```
free-agent-app/
├── app/
│   ├── main.py            # entrypoint FastAPI (uvicorn app.main:app)
│   ├── config.py  database.py  models.py  auth.py
│   ├── routers/           # auth · profile · scripts · admin
│   ├── services/          # transcription.py · generator.py
│   └── templates/         # Jinja2 (dashboard, login, profile, history, admin/)
├── static/                # css · js · thumbnails
├── requirements.txt       # producción (PostgreSQL)
├── requirements-local.txt # desarrollo (SQLite + instaloader)
└── nixpacks.toml          # build (postgresql + ffmpeg)
```

## Despliegue

Corre en un servidor **Hetzner** en `/var/www/freeagent` con **Nixpacks** (instala `postgresql` y `ffmpeg`). Comando de arranque:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Repositorio: [`github.com/herramientassielmann-tech/free-agent-app`](https://github.com/herramientassielmann-tech/free-agent-app)

> ⚠️ **SQLite no sirve en plataformas con filesystem efímero** (Railway, etc.): usa siempre PostgreSQL en producción. Los audios temporales de TikTok/IG se borran solos tras transcribirse.

---

<sub>Proyecto privado · Free Agent Academy.</sub>
