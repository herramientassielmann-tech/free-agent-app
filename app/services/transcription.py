import shutil
import subprocess
import tempfile
import os
import uuid
from pathlib import Path
from openai import OpenAI
from app.config import OPENAI_API_KEY, INSTAGRAM_COOKIES_FILE

THUMBNAILS_DIR = Path("static/thumbnails")
THUMB_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
WHISPER_EXTS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}


def _detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "instagram.com" in url_lower:
        return "instagram"
    return "unknown"


def _whisper_transcribe(audio_path: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
    return result.text


def _save_thumbnail(src: Path) -> str | None:
    """Copia un archivo de thumbnail al directorio permanente y devuelve la URL."""
    if src is None or not src.exists():
        return None
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    dest_name = f"{uuid.uuid4().hex}{src.suffix.lower()}"
    shutil.copy2(str(src), str(THUMBNAILS_DIR / dest_name))
    return f"/static/thumbnails/{dest_name}"



def _error_descarga(e: Exception, red: str) -> ValueError:
    """Traduce el fallo de yt-dlp a algo que el realtor pueda entender y accionar.

    Sin esto sale un 500 con la traza técnica y parece culpa suya."""
    msg = str(e).lower()
    if "rate-limit" in msg or "login required" in msg or "not available" in msg:
        return ValueError(
            f"{red} no nos ha dejado descargar este vídeo. Suele pasar si el vídeo "
            "es privado, se ha borrado, o si la cuenta desde la que descargamos "
            "necesita renovarse. Prueba con otro vídeo; si fallan todos, avisa al "
            "administrador."
        )
    if "ip address is blocked" in msg:
        return ValueError(
            f"{red} está bloqueando temporalmente al servidor. Vuelve a intentarlo "
            "en un rato; si sigue igual, avisa al administrador."
        )
    if "private" in msg or "unavailable" in msg:
        return ValueError(
            f"Este vídeo de {red} es privado o ya no existe. Prueba con otro."
        )
    return ValueError(
        f"No se pudo descargar el vídeo de {red}. Comprueba que el enlace es "
        "correcto y que el vídeo es público."
    )


# ── Instagram via yt-dlp + cookies ──────────────────────────────────────────

def _instagram_download(url: str) -> dict:
    """Descarga audio y thumbnail de un reel/post de Instagram con yt-dlp y cookies."""
    import yt_dlp

    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    cookies_path = Path(INSTAGRAM_COOKIES_FILE) if INSTAGRAM_COOKIES_FILE else None

    if not cookies_path or not cookies_path.exists():
        raise ValueError(
            "No se encontró el archivo de cookies de Instagram en el servidor. "
            "Contacta al administrador para renovarlas."
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        # yt-dlp REESCRIBE el fichero de cookies al terminar. Si Instagram
        # invalida la sesión, guarda el fichero ya sin `sessionid` y destruye la
        # credencial para siempre. Por eso trabaja sobre una copia desechable:
        # el fichero bueno del servidor no se toca nunca.
        cookies_copia = os.path.join(tmpdir, "cookies.txt")
        shutil.copyfile(cookies_path, cookies_copia)

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "media.%(ext)s"),
            "writethumbnail": True,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookies_copia,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            raise _error_descarga(e, "Instagram") from e

        transcript = None
        thumbnail_tmp = None
        for f in Path(tmpdir).iterdir():
            if f.suffix.lower() in WHISPER_EXTS and transcript is None:
                transcript = _whisper_transcribe(str(f))
            elif f.suffix.lower() in THUMB_EXTS and thumbnail_tmp is None:
                thumbnail_tmp = f

        if transcript is None:
            raise ValueError("No se pudo descargar el audio del vídeo de Instagram.")

        thumbnail_path = _save_thumbnail(thumbnail_tmp)

    return {"transcript": transcript, "thumbnail_path": thumbnail_path}


# ── TikTok via yt-dlp ────────────────────────────────────────────────────────

def _tiktok_download(url: str) -> dict:
    """Descarga vídeo de TikTok y extrae frame con ffmpeg para thumbnail."""
    import yt_dlp

    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(tmpdir, "media.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            raise _error_descarga(e, "TikTok") from e

        video_file = next(
            (f for f in Path(tmpdir).iterdir() if f.suffix.lower() in WHISPER_EXTS),
            None,
        )
        if video_file is None:
            raise ValueError("No se pudo descargar el vídeo de TikTok.")

        thumb_tmp = Path(tmpdir) / "thumb.jpg"
        subprocess.run(
            ["ffmpeg", "-i", str(video_file), "-ss", "00:00:01",
             "-vframes", "1", "-q:v", "2", str(thumb_tmp), "-y", "-loglevel", "quiet"],
            check=False,
            capture_output=True,
        )

        transcript = _whisper_transcribe(str(video_file))
        thumbnail_path = _save_thumbnail(thumb_tmp if thumb_tmp.exists() else None)

    return {"transcript": transcript, "thumbnail_path": thumbnail_path}


# ── Punto de entrada público ──────────────────────────────────────────────────

def get_transcript(url: str) -> dict:
    """Extrae transcripción y thumbnail de un vídeo de TikTok o Instagram."""
    platform = _detect_platform(url)
    if platform == "unknown":
        raise ValueError(
            "URL no reconocida. Por favor usa una URL de TikTok o Instagram."
        )
    if platform == "instagram":
        return _instagram_download(url)
    return _tiktok_download(url)
