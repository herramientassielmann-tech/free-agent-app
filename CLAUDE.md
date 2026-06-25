# CLAUDE.md — Free Agent Academy

Contrato de trabajo para Claude. El "qué es" está en el README; aquí solo las reglas que cambian cómo actúo.

## Restricciones duras (no negociables)
- **Dos ficheros de dependencias, no se mezclan:**
  - `requirements-local.txt` → desarrollo (SQLite, `instaloader`, yt-dlp reciente). Es el que instalo en local.
  - `requirements.txt` → producción (PostgreSQL vía `psycopg`). Es el del servidor.
  - Si añado una dependencia, decido a cuál(es) pertenece; no la meto en ambos por inercia.
- **Base de datos:** PostgreSQL/Supabase en producción **siempre**. **Nunca** SQLite en prod (filesystem efímero la borra). Local sí puede usar SQLite.
- **Idioma del producto:** todo lo que genera la app (guiones, captions) va **en español**. No cambio esto.
- **ffmpeg** es necesario (lo usa yt-dlp para TikTok/IG).

## Convenciones del código
- Estructura por capas: rutas en `app/routers/`, lógica en `app/services/` (`transcription.py`, `generator.py`), vistas Jinja2 en `app/templates/`. Respeto esa separación.
- Entrypoint: `app.main:app`. El admin se crea solo al arrancar a partir de `ADMIN_EMAIL`/`ADMIN_PASSWORD`.

## Seguridad
- **Nunca** commiteo `.env` ni imprimo secretos (`SECRET_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, credenciales de Instagram).
- `insta_session` e `instagram_cookies.txt` son credenciales: no se versionan ni se exponen.

## Git
- Repo con remoto en GitHub (`herramientassielmann-tech/free-agent-app`). Puedo commitear; **no hago push sin confirmación**.
- No commiteo cambios de `freeagent.db` (datos locales) salvo que se pida expresamente.

## Despliegue (servidor Hetzner)
- Ruta: `/var/www/freeagent` · Python 3.14 en `.venv` · build con Nixpacks (`postgresql` + `ffmpeg`).
- Servicio: **`freeagent.service`** (systemd) → `uvicorn app.main:app --port 8001`, detrás de nginx en **tool.robertsielmann.com**.
- Tras subir cambios: `systemctl restart freeagent`. Logs: `journalctl -u freeagent -f`.
- **No despliego ni reinicio sin confirmación explícita.**

> Nota: `tool.robertsielmann.com` (esta app) y `robertsielmann.com` (la landing en LucusHost) son hosts distintos aunque compartan dominio.
