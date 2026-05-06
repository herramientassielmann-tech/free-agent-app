import re
import tempfile
import os
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from openai import OpenAI
from app.config import OPENAI_API_KEY


def _detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "instagram.com" in url_lower:
        return "instagram"
    return "unknown"


def _extract_youtube_id(url: str):
    patterns = [
        r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:embed|shorts)/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _youtube_transcript(video_id: str) -> str:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # Intentar en español primero, luego cualquier idioma
        try:
            transcript = transcript_list.find_transcript(["es", "es-419", "es-ES"])
        except Exception:
            transcript = transcript_list.find_generated_transcript(
                transcript_list._generated_transcripts.keys()
                or transcript_list._manually_created_transcripts.keys()
            )
        entries = transcript.fetch()
        return " ".join(e["text"] for e in entries)
    except (TranscriptsDisabled, NoTranscriptFound):
        raise ValueError("No hay transcripción disponible para este vídeo de YouTube.")


def _whisper_transcribe(audio_path: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    with open(audio_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
    return result.text


def _find_ffmpeg() -> str | None:
    import shutil
    # Buscar en PATH primero
    path = shutil.which("ffmpeg")
    if path:
        return path
    # Rutas comunes en Railway/Nix
    candidates = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/nix/var/nix/profiles/default/bin/ffmpeg",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    # Buscar recursivamente en /nix si existe
    nix_root = Path("/nix/store")
    if nix_root.exists():
        for p in nix_root.glob("*/bin/ffmpeg"):
            if p.is_file():
                return str(p)
    return None


def _yt_dlp_audio_then_whisper(url: str) -> str:
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
            "quiet": True,
            "no_warnings": True,
        }
        ffmpeg_path = _find_ffmpeg()
        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = str(Path(ffmpeg_path).parent)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # yt-dlp puede usar extensiones diferentes, buscamos el archivo descargado
        for f in Path(tmpdir).iterdir():
            if f.suffix in (".mp3", ".m4a", ".webm", ".ogg"):
                return _whisper_transcribe(str(f))

        raise ValueError("No se pudo descargar el audio del vídeo.")


def get_transcript(url: str) -> str:
    """
    Extrae la transcripción de texto de un vídeo dado su URL.
    Soporta YouTube, TikTok e Instagram.
    """
    platform = _detect_platform(url)

    if platform == "unknown":
        raise ValueError(
            "URL no reconocida. Por favor usa una URL de YouTube, TikTok o Instagram."
        )

    if platform == "youtube":
        video_id = _extract_youtube_id(url)
        if not video_id:
            raise ValueError("No se pudo extraer el ID del vídeo de YouTube.")
        try:
            return _youtube_transcript(video_id)
        except ValueError:
            # Fallback: descargar audio y transcribir con Whisper
            return _yt_dlp_audio_then_whisper(url)

    # TikTok e Instagram: siempre via yt-dlp + Whisper
    return _yt_dlp_audio_then_whisper(url)
