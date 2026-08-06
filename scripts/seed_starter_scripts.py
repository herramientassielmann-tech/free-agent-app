"""Genera los guiones de "Ideas Iniciales" a partir de una lista de vídeos.

Se ejecuta UNA sola vez (o para reintentar los que fallen): pasa cada enlace
por el mismo pipeline que usa la app cuando un realtor genera un guión
(descarga + transcripción con Whisper + generación con la metodología), y
guarda el resultado como contenido común de la academia.

Es idempotente: si un enlace ya está en la BD, lo salta. Así se puede
relanzar para reintentar solo los que fallaron.

Uso (desde /var/www/freeagent):
    .venv/bin/python3 scripts/seed_starter_scripts.py            # todos
    .venv/bin/python3 scripts/seed_starter_scripts.py --limit 1  # prueba
"""
import sys
import argparse
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic
from app.config import ANTHROPIC_API_KEY
from app.database import SessionLocal, engine
from app.models import Base, StarterScript
from app.services.transcription import get_transcript
from app.services.generator import generate_script

# Los 23 vídeos seleccionados. El orden aquí es el orden en que se muestran.
VIDEO_URLS = [
    "https://www.instagram.com/reels/DTnf5cBAqDs/",
    "https://www.instagram.com/reel/DY5aYNJDuv-/",
    "https://www.instagram.com/reels/DSvR_T8jKEr/",
    "https://www.instagram.com/reels/DWeVdgcjLtU/",
    "https://www.instagram.com/reel/DLXe_yIgmXz/",
    "https://www.instagram.com/reel/DaTo9-BJj2j/",
    "https://www.instagram.com/reel/DRGJhpzjo9O/",
    "https://www.instagram.com/reel/DHVv509oPIL/",
    "https://www.instagram.com/reel/DRk_B5BDlxH/",
    "https://www.instagram.com/reel/DZ436ikDoQJ/",
    "https://www.instagram.com/reel/DKFRzMqItaT/",
    "https://www.instagram.com/reel/DXc-ejkAM88/",
    "https://www.instagram.com/reel/DVCdJ7Ijh_l/",
    "https://www.instagram.com/reel/DWhoBHyDkf_/",
    "https://www.instagram.com/reels/DVl4I-wDVTw/",
    "https://www.instagram.com/reel/DavMJoIOjSv/",
    "https://www.instagram.com/reel/DZyAL3rNjJr/",
    "https://www.instagram.com/reel/DR3DKS5DvaP/",
    "https://www.instagram.com/reel/DZ56s2fucur/",
    "https://www.instagram.com/reels/C8pr7zrB2-0/",
    "https://www.instagram.com/reel/DXHo-ywiIdn/",
    "https://www.instagram.com/reel/DVB2sIvDBT2/",
    "https://www.instagram.com/reel/DavN2YwuuiE/",
]

# Perfil neutro: estos guiones son comunes a TODOS los realtors, así que no
# se personalizan a la zona ni al estilo de ninguno en concreto.
GENERIC_USER = SimpleNamespace(name="el realtor")
GENERIC_PROFILE = SimpleNamespace(
    display_name=None,
    market="tu zona",
    tone="cercano",
    specialization="todo_tipo",
    speaking_notes=None,
    about_me=None,
    cliente_ideal=None,
    objeciones=None,
    casos_exito=None,
    objetivo_cta=None,
    temas_evitar=None,
)


def short_title(hook: str, estructura: str) -> str:
    """Título corto y escaneable para la lista de ideas (Haiku, ~0,001 $)."""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=60,
            system=(
                "Escribe un título corto (máximo 6 palabras) en español que resuma "
                "de qué va este guión de vídeo inmobiliario. Responde SOLO con el "
                "título, sin comillas ni puntos finales."
            ),
            messages=[{"role": "user", "content": f"Guión: {hook}\n\nContexto: {estructura}"}],
        )
        block = next((b for b in msg.content if b.type == "text"), None)
        if block:
            return block.text.strip().strip('"').strip(".")[:200]
    except Exception as e:
        print(f"    (aviso: no se pudo generar título: {e})")
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="procesar solo N enlaces")
    parser.add_argument("--only", type=str, default="", help="procesar solo el enlace que contenga este texto")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    urls = VIDEO_URLS
    if args.only:
        urls = [u for u in urls if args.only in u]
    if args.limit:
        urls = urls[: args.limit]

    ok, fallidos, saltados = 0, [], 0

    for idx, url in enumerate(urls, start=1):
        position = VIDEO_URLS.index(url) + 1
        existing = db.query(StarterScript).filter(StarterScript.source_url == url).first()
        if existing:
            print(f"[{idx}/{len(urls)}] SALTADO (ya existe): {url}")
            saltados += 1
            continue

        print(f"[{idx}/{len(urls)}] Procesando: {url}")
        try:
            print("    · descargando y transcribiendo…")
            trans = get_transcript(url)
            transcript = trans["transcript"]
            thumbnail_path = trans.get("thumbnail_path")

            print(f"    · transcripción OK ({len(transcript.split())} palabras), generando guión…")
            result = generate_script(
                transcript=transcript,
                user=GENERIC_USER,
                profile=GENERIC_PROFILE,
                custom_instructions="",
            )

            titulo = short_title(result["hook"], result.get("estructura_detectada", ""))

            db.add(StarterScript(
                position=position,
                source_url=url,
                titulo=titulo or None,
                hook=result["hook"],
                development=result["desarrollo"],
                conclusion=result["conclusion"],
                caption=result["caption"],
                estructura_detectada=result.get("estructura_detectada"),
                thumbnail_path=thumbnail_path,
            ))
            db.commit()
            ok += 1
            print(f"    ✅ guardado — «{titulo or result['hook'][:50]}»")
        except Exception as e:
            db.rollback()
            fallidos.append((url, str(e)[:200]))
            print(f"    ❌ FALLÓ: {str(e)[:200]}")

    print()
    print("═══════════ RESUMEN ═══════════")
    print(f"Generados: {ok} | Saltados (ya estaban): {saltados} | Fallidos: {len(fallidos)}")
    if fallidos:
        print("\nFallidos (relanza el script para reintentarlos):")
        for u, e in fallidos:
            print(f"  - {u}\n      {e}")
    total = db.query(StarterScript).count()
    print(f"\nTotal de guiones en la BD: {total}")
    db.close()


if __name__ == "__main__":
    main()
