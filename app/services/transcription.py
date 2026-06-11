import shutil
import tempfile
import os
import uuid
from pathlib import Path
from openai import OpenAI
from app.config import OPENAI_API_KEY

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


def _yt_dlp_audio_then_whisper(url: str) -> dict:
    """Returns {"transcript": str, "thumbnail_path": str | None}"""
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
            elif f.suffix.lower() in THUMB_EXTS:
                thumbnail_tmp = f

        if transcript is None:
            raise ValueError("No se pudo descargar el audio del vídeo.")

        thumbnail_path = None
        if thumbnail_tmp is not None:
            dest_name = f"{uuid.uuid4().hex}{thumbnail_tmp.suffix.lower()}"
            dest = THUMBNAILS_DIR / dest_name
            shutil.copy2(str(thumbnail_tmp), str(dest))
            thumbnail_path = f"/static/thumbnails/{dest_name}"

    return {"transcript": transcript, "thumbnail_path": thumbnail_path}


def get_transcript(url: str) -> dict:
    """Extrae transcripción y thumbnail de un vídeo de TikTok o Instagram."""
    platform = _detect_platform(url)

    if platform == "unknown":
        raise ValueError(
            "URL no reconocida. Por favor usa una URL de TikTok o Instagram."
        )

    return _yt_dlp_audio_then_whisper(url)
