#!/usr/bin/env python3
"""
OCR automatikus fényképfelismerés GPT-4o mini Visionnel.
Automatikusan megtalálja és feldolgozza a könyvtárban található képeket.

$ python pictureread.py
"""
import base64
import sys
from pathlib import Path
from dotenv import load_dotenv
import os
from openai import OpenAI
from PIL import Image
import glob

# ─── Beállítások ──────────────────────────────────────────────────────────────

MODEL_NAME = "gpt-4o-mini"          # Vision-képes modell
DETAIL_LEVEL = "high"               # "low" olcsóbb, de pontatlanabb lehet
MAX_TOKENS = 1000                   # OCR-válasz hossz (igény szerint)

# Támogatott képformátumok
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic'}

# ─── Segédfüggvények ──────────────────────────────────────────────────────────

def find_images_in_directory(directory: Path = None) -> list[Path]:
    """
    Megkeresi az összes képfájlt a megadott könyvtárban.
    Ha nincs megadva könyvtár, az aktuális könyvtárat használja.
    """
    if directory is None:
        directory = Path.cwd()
    
    image_files = []
    for ext in SUPPORTED_EXTENSIONS:
        pattern = f"*{ext}"
        image_files.extend(directory.glob(pattern))
        # Nagy betűs kiterjesztések is
        pattern = f"*{ext.upper()}"
        image_files.extend(directory.glob(pattern))
    
    return sorted(image_files)

def image_to_base64(image_path: Path) -> str:
    """
    Betölt egy képet, biztosítja a JPEG/PNG formátumot, és base64-re kódolja.
    """
    # Ha nem JPEG/PNG, konvertáljuk (pl. HEIC → JPEG) a PIL segítségével
    if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        img = Image.open(image_path)
        temp_path = image_path.with_suffix(".jpg")
        img.save(temp_path, format="JPEG", quality=95)
        image_path = temp_path

    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def process_image(client: OpenAI, img_path: Path) -> None:
    """
    Feldolgoz egy képet és kiírja az OCR eredményt.
    """
    print(f"→ Feldolgozás: {img_path.name}")
    
    try:
        b64_image = image_to_base64(img_path)
        
        print("  Kép elküldése a GPT-4o-nak…")
        response = client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Kérlek, olvasd el és írd le a képen látható minden szöveget pontosan úgy, ahogy látod. Ha nincs szöveg a képen, akkor írd le, hogy mit látsz."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": DETAIL_LEVEL
                            },
                        },
                    ],
                }
            ],
        )

        # Token használat megjelenítése
        usage = response.usage
        print(f"  💡 Token használat: {usage.prompt_tokens} prompt + {usage.completion_tokens} completion = {usage.total_tokens} összesen")

        print(f"\n── Felismert szöveg ({img_path.name}) ──")
        print(response.choices[0].message.content.strip())
        print("\n" + "="*50 + "\n")
        
    except Exception as e:
        print(f"  Hiba a kép feldolgozása során: {e}")

# ─── Főprogram ────────────────────────────────────────────────────────────────

def main() -> None:
    # .env betöltése → OPENAI_API_KEY környezeti változó
    load_dotenv()
    if os.getenv("OPENAI_API_KEY") is None:
        sys.exit("Hiányzik az OPENAI_API_KEY a környezeti változók közül!")

    client = OpenAI()  # kulcsot implicit módon veszi a környezeti változóból

    # Képek keresése az aktuális könyvtárban
    current_dir = Path.cwd()
    image_files = find_images_in_directory(current_dir)
    
    if not image_files:
        print("Nem találtam képfájlokat az aktuális könyvtárban.")
        print(f"Támogatott formátumok: {', '.join(SUPPORTED_EXTENSIONS)}")
        return
    
    print(f"Találtam {len(image_files)} képfájlt:")
    for img in image_files:
        print(f"  - {img.name}")
    print()
    
    # Minden kép feldolgozása
    for img_path in image_files:
        process_image(client, img_path)


if __name__ == "__main__":
    main()
