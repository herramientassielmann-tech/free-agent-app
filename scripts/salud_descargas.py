"""Vigila que generar guiones sigue funcionando, y lo arregla solo si puede.

Contexto: esto ha fallado dos veces en producción y las dos veces se enteraron
antes los alumnos que nosotros.

  · Agosto 2026 — yt-dlp desactualizado. Diez días sin poder generar.
  · Septiembre 2026 — Whisper rechazaba el mp4 de TikTok. Fallaban unos vídeos
    sí y otros no, que es lo que más cuesta de ver.

La primera versión de este script solo miraba si yt-dlp podía LEER el vídeo.
Eso no habría cogido el segundo fallo: la descarga funcionaba perfectamente y
lo que reventaba era la transcripción, un paso más allá. Por eso ahora se
prueba la cadena completa —descargar, extraer el audio y transcribirlo con
Whisper—, que es exactamente lo que hace un realtor al pegar una URL.

Qué hace cuando algo falla, sin preguntar a nadie:

  1. Actualiza yt-dlp. Instagram y TikTok cambian sus extractores cada pocas
     semanas y esto es lo que arregló el incidente de agosto.
  2. Reinicia el servicio. Esto NO es opcional ni cosmético: el proceso de
     uvicorn ya tiene el yt-dlp viejo importado en memoria, así que sin
     reiniciar la actualización no llega a los alumnos.
  3. Vuelve a probar. Si se arregló, avisa por email de que pasó algo y se
     resolvió solo. Si sigue roto, avisa de que hace falta una persona.

No manda correo cuando todo va bien. Un aviso diario de «todo correcto» se
acaba filtrando, y el día que llega el de verdad ya nadie lo abre.

Solo da por caída una plataforma si fallan TODOS sus vídeos de prueba: si falla
uno suelto, lo más probable es que lo hayan borrado.

Uso:
    .venv/bin/python3 scripts/salud_descargas.py
    .venv/bin/python3 scripts/salud_descargas.py --sin-arreglar   # solo mirar

Sale con código 1 si algo sigue roto tras intentar arreglarlo.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ESTADO = RAIZ / "estado_descargas.json"
PYTHON = str(RAIZ / ".venv" / "bin" / "python3")

# Varios por plataforma: un vídeo borrado no debe disparar la alarma.
# Verificados el 10/09/2026.
CANARIOS = {
    "Instagram": [
        "https://www.instagram.com/reel/DM8Tu1IR85X/",
        "https://www.instagram.com/reel/DczLCBUjvww/",
    ],
    "TikTok": [
        "https://www.tiktok.com/@nacho.jauz/video/7554538320064204088",
        "https://www.tiktok.com/@sellitdotcom/video/7429812565460438314",
    ],
}


def _version_ytdlp() -> str:
    try:
        r = subprocess.run([PYTHON, "-m", "yt_dlp", "--version"],
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip() or "desconocida"
    except Exception:
        return "desconocida"


def _probar_cadena(url: str) -> tuple:
    """Recorre la cadena entera como lo haría un realtor. (ok, detalle)

    Se llama a get_transcript, la misma función que usa /generate, para que la
    prueba no pueda quedarse desalineada con lo que vive el alumno.
    """
    try:
        from app.services.transcription import get_transcript
        r = get_transcript(url)
        texto = (r.get("transcript") or "").strip()

        # El thumbnail se guarda en disco; aquí no queremos ir dejando uno
        # cada día.
        thumb = r.get("thumbnail_path")
        if thumb:
            f = RAIZ / thumb.lstrip("/")
            if f.exists():
                f.unlink()

        if not texto:
            return False, "transcripción vacía"
        return True, f"{len(texto)} caracteres"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def _revisar() -> dict:
    """Estado por plataforma. Solo se da por rota si fallan todos sus vídeos."""
    resultado = {}
    for plataforma, urls in CANARIOS.items():
        ok, detalles = 0, []
        for u in urls:
            bien, detalle = _probar_cadena(u)
            detalles.append(detalle)
            if bien:
                ok += 1
                break   # con uno que funcione basta; no gastamos más Whisper
        resultado[plataforma] = {
            "ok": ok > 0,
            "funcionan": ok,
            "probados": len(detalles),
            "detalle": detalles[-1] if detalles else "",
        }
    return resultado


def _actualizar_ytdlp() -> str:
    antes = _version_ytdlp()
    subprocess.run([PYTHON, "-m", "pip", "install", "-q", "--upgrade", "yt-dlp"],
                   capture_output=True, timeout=600)
    despues = _version_ytdlp()
    return f"{antes} → {despues}" + ("" if antes != despues else " (ya estaba al día)")


def _reiniciar_servicio() -> bool:
    """Sin esto la actualización de yt-dlp no llega a los alumnos: el proceso
    de uvicorn ya tiene el módulo viejo importado en memoria."""
    try:
        r = subprocess.run(["systemctl", "restart", "freeagent"],
                           capture_output=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False


def _avisar(asunto: str, lineas: list) -> None:
    """Correo al administrador. Nunca tumba el script si falla el envío."""
    try:
        from app.config import ADMIN_EMAIL
        from app.services.email import enviar, esta_configurado
        if not esta_configurado():
            return
        cuerpo = "".join(f"<p style='margin:0 0 8px'>{l}</p>" for l in lineas)
        enviar(
            ADMIN_EMAIL,
            asunto,
            f"<div style=\"font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;"
            f"font-size:15px;color:#16202C;line-height:1.5\">{cuerpo}</div>",
            "\n".join(lineas),
        )
    except Exception as e:
        print(f"  (no se pudo avisar por email: {e})")


def main() -> int:
    arreglar = "--sin-arreglar" not in sys.argv[1:]
    ahora = datetime.utcnow()

    estado = _revisar()
    rotas = [p for p, r in estado.items() if not r["ok"]]
    actualizacion = reiniciado = None

    if rotas and arreglar:
        print(f"Fallan: {', '.join(rotas)}. Intentando arreglarlo solo…")
        actualizacion = _actualizar_ytdlp()
        print(f"  yt-dlp {actualizacion}")
        reiniciado = _reiniciar_servicio()
        print(f"  reinicio del servicio: {'hecho' if reiniciado else 'FALLÓ'}")
        estado = _revisar()
        rotas = [p for p, r in estado.items() if not r["ok"]]

    salida = {
        "revisado": ahora.isoformat(timespec="seconds") + "Z",
        "yt_dlp": _version_ytdlp(),
        "actualizacion": actualizacion,
        "reiniciado": reiniciado,
        "plataformas": estado,
        "rotas": rotas,
    }
    ESTADO.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

    for p, r in estado.items():
        print(f"  {p}: {'OK' if r['ok'] else 'ROTO'} — {r['detalle']}")

    if rotas:
        print(f"\nSIGUEN ROTAS: {', '.join(rotas)}")
        _avisar(
            f"⚠️ Los guiones no se generan ({', '.join(rotas)})",
            [f"<b>{', '.join(rotas)}</b> sigue fallando después de intentar arreglarlo solo.",
             f"Detalle: {'; '.join(r['detalle'] for p, r in estado.items() if not r['ok'])}",
             f"yt-dlp: {actualizacion or _version_ytdlp()}",
             f"Reinicio del servicio: {'hecho' if reiniciado else 'no se pudo'}",
             "Esto necesita una persona. Los alumnos no pueden generar guiones ahora mismo."],
        )
        return 1

    if actualizacion:
        print(f"\nSe arregló solo.")
        _avisar(
            "✅ Los guiones fallaban y se ha arreglado solo",
            ["Algo dejó de funcionar esta madrugada y el vigilante lo ha resuelto sin intervención.",
             f"yt-dlp: {actualizacion}",
             f"Reinicio del servicio: {'hecho' if reiniciado else 'no hizo falta'}",
             "Ahora mismo Instagram y TikTok vuelven a generar correctamente. No hay que hacer nada."],
        )
        return 0

    print("\nTodo correcto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
