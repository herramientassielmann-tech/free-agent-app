import tempfile
import os
from pathlib import Path
from openai import OpenAI
from app.config import OPENAI_API_KEY


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


def _yt_dlp_audio_then_whisper(url: str) -> str:
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        WHISPER_EXTS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
        for f in Path(tmpdir).iterdir():
            if f.suffix.lower() in WHISPER_EXTS:
                return _whisper_transcribe(str(f))

        raise ValueError("No se pudo descargar el audio del vídeo.")


def get_transcript(url: str) -> str:
    """Extrae la transcripción de un vídeo de TikTok o Instagram."""
    platform = _detect_platform(url)

    if platform == "unknown":
        raise ValueError(
            "URL no reconocida. Por favor usa una URL de TikTok o Instagram."
        )

    return _yt_dlp_audio_then_whisper(url)
