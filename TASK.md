# Free Agent Academy — Generador de Guiones

## Descripción
Plataforma web para realtors hispanohablantes que convierte vídeos virales (YouTube, TikTok, Instagram) en guiones personalizados con estructura Hook–Desarrollo–Conclusión más caption listo para publicar, siempre en español y adaptado al perfil de cada realtor.

## Cuándo usar este script
- "Genera un guión a partir de este vídeo"
- "Adapta este TikTok para mi perfil de realtor"
- "Quiero usar este vídeo viral para mi canal"

## Prerequisitos
- Python 3.11+
- Variables de entorno configuradas en `.env` (ver `.env.example`)
- Dependencias instaladas: `pip install -r requirements.txt`
- `ffmpeg` instalado en el sistema (necesario para yt-dlp): `brew install ffmpeg` (Mac) o `apt install ffmpeg` (Linux)

## Cómo ejecutar

### Desarrollo local
```bash
cp .env.example .env
# Editar .env con tus claves reales
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Abrir: http://localhost:8000

### Producción (Railway / Render)
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Variables de entorno: configurar en el panel de Railway/Render
- DATABASE_URL: usar la URL de PostgreSQL proporcionada por la plataforma

## Variables de Entorno Requeridas
| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave para firmar JWT |
| `ANTHROPIC_API_KEY` | Claude API para generación de guiones |
| `OPENAI_API_KEY` | Whisper API para transcribir TikTok/Instagram |
| `ADMIN_EMAIL` | Email del administrador inicial |
| `ADMIN_PASSWORD` | Contraseña del administrador inicial |
| `DATABASE_URL` | URL de base de datos (SQLite o PostgreSQL) |

## Estructura de la Aplicación
- `/` → Dashboard (generador de guiones)
- `/login` → Autenticación
- `/profile` → Configuración del perfil del realtor
- `/history` → Historial de guiones generados
- `/admin` → Panel de administración (solo admins)

## Notas
- Los archivos de audio temporales (TikTok/IG) se eliminan automáticamente tras la transcripción.
- El admin inicial se crea automáticamente al primer arranque si no existe en la DB.
- Para SQLite en producción: no funciona en plataformas con filesystem efímero (Railway). Usar PostgreSQL.
