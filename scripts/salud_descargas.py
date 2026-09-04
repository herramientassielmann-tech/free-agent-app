"""Vigila que las descargas de Instagram y TikTok siguen funcionando.

Contexto: en agosto de 2026 los realtors estuvieron diez días sin poder generar
guiones y nadie se enteró. La causa fue yt-dlp desactualizado — Instagram y
TikTok cambian sus extractores cada pocas semanas y yt-dlp los persigue versión
a versión. Es un fallo que se repetirá, así que conviene detectarlo solo.

Qué hace, en orden:
  1. Pide los metadatos de varios vídeos conocidos (sin descargar nada, es rápido).
  2. Si una plataforma falla, actualiza yt-dlp y lo reintenta — que es
     exactamente lo que arregló el incidente.
  3. Escribe el resultado en un fichero de estado que el panel de admin lee.

Solo da por caída una plataforma si fallan TODOS sus vídeos de prueba: si falla
uno suelto, lo más probable es que lo hayan borrado, no que esté rota la descarga.

Uso:
    .venv/bin/python3 scripts/salud_descargas.py

Sale con código 1 si algo sigue roto tras el intento de arreglo, para que
systemd lo registre como fallo.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "estado_descargas.json"
PYTHON = str(RAIZ / ".venv" / "bin" / "python3")

# Varios por plataforma: un vídeo borrado no debe disparar la alarma.
CANARIOS = {
    "Instagram": [
        "https://www.instagram.com/reel/DczLCBUjvww/",
        "https://www.instagram.com/reel/DcgrOTuK1QN/",
    ],
    "TikTok": [
        "https://www.tiktok.com/@olivaochoarealtesa/video/7506337417117355272",
        "https://www.tiktok.com/@dralexdeyoficial/video/7520426829790989573",
    ],
}


def _version_ytdlp() -> str:
    try:
        r = subprocess.run([PYTHON, "-m", "yt_dlp", "--version"],
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip() or "desconocida"
    except Exception:
        return "desconocida"


def _funciona(url: str, cookies: Path = None) -> bool:
    """True si yt-dlp puede leer los metadatos del vídeo."""
    cmd = [PYTHON, "-m", "yt_dlp", "--skip-download", "--no-warnings",
           "--print", "%(title)s"]
    if cookies and cookies.exists():
        cmd += ["--cookies", str(cookies)]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and bool(r.stdout.strip())
    except subprocess.TimeoutExpired:
        return False


def _revisar() -> dict:
    """Estado por plataforma. Rota solo si fallan todos sus vídeos."""
    # Se pasa una COPIA de las cookies: yt-dlp reescribe el fichero y un fallo
    # borraría el sessionid del bueno.
    cookies_orig = RAIZ / "instagram_cookies.txt"
    resultado = {}
    for plataforma, urls in CANARIOS.items():
        cookies = cookies_orig if plataforma == "Instagram" else None
        if cookies and cookies.exists():
            import shutil, tempfile
            tmp = Path(tempfile.mkdtemp()) / "cookies.txt"
            shutil.copyfile(cookies, tmp)
            cookies = tmp
        ok = sum(1 for u in urls if _funciona(u, cookies))
        resultado[plataforma] = {"ok": ok > 0, "funcionan": ok, "probados": len(urls)}
    return resultado


def _actualizar_ytdlp() -> str:
    antes = _version_ytdlp()
    subprocess.run([PYTHON, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"],
                   capture_output=True, timeout=600)
    return f"{antes} -> {_version_ytdlp()}"


def main():
    estado = _revisar()
    rotas = [p for p, r in estado.items() if not r["ok"]]
    actualizacion = None

    if rotas:
        print(f"Fallan: {', '.join(rotas)}. Actualizando yt-dlp…")
        actualizacion = _actualizar_ytdlp()
        print(f"  yt-dlp {actualizacion}")
        estado = _revisar()
        rotas = [p for p, r in estado.items() if not r["ok"]]

    salida = {
        "revisado": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "yt_dlp": _version_ytdlp(),
        "actualizacion": actualizacion,
        "plataformas": estado,
        "rotas": rotas,
    }
    ESTADO.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

    for p, r in estado.items():
        print(f"  {p}: {'OK' if r['ok'] else 'ROTO'} ({r['funcionan']}/{r['probados']})")

    if rotas:
        print(f"\nSIGUEN ROTAS tras actualizar: {', '.join(rotas)}")
        return 1
    print("\nTodo correcto." + (" Se arregló actualizando yt-dlp." if actualizacion else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
