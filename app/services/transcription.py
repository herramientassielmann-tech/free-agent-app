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


# Whisper acepta hasta 25 MB. A 64 kbps mono, eso son casi 50 minutos de audio:
# ningún reel se acerca, así que el límite deja de ser un problema en cuanto se
# manda audio en vez de vídeo.
LIMITE_WHISPER_MB = 24


def _extraer_audio(origen: Path, destino: Path) -> bool:
    """Saca la pista de audio del vídeo con ffmpeg. True si lo consiguió.

    Por qué no mandar el vídeo directamente, que es lo que se hacía antes:
    Whisper acepta contenedores de vídeo, pero solo algunos, y TikTok e
    Instagram cambian de códec sin avisar. Un mp4 que ayer entraba hoy devuelve
    400 y el realtor ve un error 500 sin explicación. Extrayendo el audio a mp3
    mono de 16 kHz —que es justo lo que Whisper usa por dentro— el formato deja
    de depender de lo que sirva la plataforma, el fichero pasa de 15 MB a menos
    de 1, y sube más rápido.
    """
    r = subprocess.run(
        ["ffmpeg", "-i", str(origen), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "libmp3lame", "-b:a", "64k", str(destino), "-y", "-loglevel", "error"],
        check=False,
        capture_output=True,
    )
    return r.returncode == 0 and destino.exists() and destino.stat().st_size > 0


def _transcribir(media: Path, red: str) -> str:
    """Transcribe un fichero descargado, extrayendo antes el audio.

    Cualquier fallo sale traducido: un 500 con la traza dentro hace que el
    realtor crea que ha hecho algo mal y deje de intentarlo.
    """
    audio = media.with_name("audio_extraido.mp3")
    if _extraer_audio(media, audio):
        fichero = audio
    else:
        # Sin pista de audio no hay nada que transcribir. Es un vídeo mudo,
        # o la descarga trajo solo la imagen.
        if not _tiene_audio(media):
            raise ValueError(
                f"Este vídeo de {red} no tiene audio, así que no hay nada que "
                "transcribir. Prueba con otro vídeo en el que se hable."
            )
        fichero = media  # ffmpeg falló pero hay audio: probamos tal cual

    tam_mb = fichero.stat().st_size / 1024 / 1024
    if tam_mb > LIMITE_WHISPER_MB:
        raise ValueError(
            f"Este vídeo es demasiado largo para transcribirlo ({tam_mb:.0f} MB de "
            "audio). Prueba con un vídeo más corto."
        )

    try:
        return _whisper_transcribe(str(fichero))
    except Exception as e:
        raise ValueError(
            f"No se pudo transcribir el audio de este vídeo de {red}. "
            "Suele ser cosa del vídeo en concreto: prueba con otro y, si fallan "
            "varios seguidos, avisa al administrador."
        ) from e


def _tiene_audio(media: Path) -> bool:
    """True si el fichero trae al menos una pista de audio."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(media)],
        check=False,
        capture_output=True,
        text=True,
    )
    return "audio" in (r.stdout or "")


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
                transcript = _transcribir(f, "Instagram")
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

        transcript = _transcribir(video_file, "TikTok")
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
