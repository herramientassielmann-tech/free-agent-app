import re
import shutil
import tempfile
import os
import uuid
from pathlib import Path
from openai import OpenAI
from app.config import OPENAI_API_KEY, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, INSTAGRAM_SESSION_FILE

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


# ── Instagram via instaloader ────────────────────────────────────────────────

def _instaloader_login(L):
    """Hace login en Instagram y guarda la sesión para reutilizarla."""
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        raise ValueError(
            "Se requieren INSTAGRAM_USERNAME e INSTAGRAM_PASSWORD en el .env "
            "para descargar vídeos de Instagram."
        )
    L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    if INSTAGRAM_SESSION_FILE:
        Path(INSTAGRAM_SESSION_FILE).parent.mkdir(parents=True, exist_ok=True)
        L.save_session_to_file(INSTAGRAM_SESSION_FILE)


def _get_instaloader():
    """Devuelve un Instaloader autenticado, reutilizando sesión guardada si existe."""
    import instaloader
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=True,
        save_metadata=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )
    session_path = Path(INSTAGRAM_SESSION_FILE) if INSTAGRAM_SESSION_FILE else None
    if session_path and session_path.exists() and INSTAGRAM_USERNAME:
        try:
            L.load_session_from_file(INSTAGRAM_USERNAME, str(session_path))
            return L
        except Exception:
            pass
    _instaloader_login(L)
    return L


def _instagram_download(url: str) -> dict:
    """Descarga audio y thumbnail de un post/reel de Instagram con instaloader."""
    import instaloader

    match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
    if not match:
        raise ValueError(
            "No se pudo extraer el ID del vídeo de la URL de Instagram. "
            "Asegúrate de que la URL sea de un post, reel o vídeo de Instagram."
        )
    shortcode = match.group(1)
    L = _get_instaloader()

    with tempfile.TemporaryDirectory() as tmpdir:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, target=Path(tmpdir))

        video_file = None
        thumb_file = None
        for f in sorted(Path(tmpdir).rglob("*")):
            if f.suffix.lower() == ".mp4" and video_file is None:
                video_file = f
            elif f.suffix.lower() in {".jpg", ".jpeg"} and thumb_file is None:
                thumb_file = f

        if video_file is None:
            raise ValueError("No se encontró el vídeo en el post de Instagram.")

        transcript = _whisper_transcribe(str(video_file))
        thumbnail_path = _save_thumbnail(thumb_file)

    return {"transcript": transcript, "thumbnail_path": thumbnail_path}


# ── TikTok via yt-dlp ────────────────────────────────────────────────────────

def _tiktok_download(url: str) -> dict:
    """Descarga audio y thumbnail de un vídeo de TikTok con yt-dlp."""
    import yt_dlp

    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "media.%(ext)s"),
            "writethumbnail": True,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        transcript = None
        thumbnail_tmp = None
        for f in Path(tmpdir).iterdir():
            if f.suffix.lower() in WHISPER_EXTS and transcript is None:
                transcript = _whisper_transcribe(str(f))
            elif f.suffix.lower() in THUMB_EXTS and thumbnail_tmp is None:
                thumbnail_tmp = f

        if transcript is None:
            raise ValueError("No se pudo descargar el audio del vídeo de TikTok.")

        thumbnail_path = _save_thumbnail(thumbnail_tmp)

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
