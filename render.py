import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction et Normalisation (Vertical 9:16)
    # On booste la netteté et la saturation pour un look "Pro"
    vf_base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:1.0,eq=saturation=1.4"

    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout: fout.write(base64.b64decode(v['data']))

    # --- ÉTAPE A : LE HOOK (1.2s) ---
    # Zoom progressif pour "aspirer" l'attention immédiatement
    os.system(f"ffmpeg -i r0.mp4 -t 1.2 -vf \"{vf_base},zoompan=z='min(zoom+0.002,1.5)':d=1:s=1080x1920\" -c:v libx264 -preset ultrafast h.mp4")

    # --- ÉTAPE B : LE CORE "JUMP-CUT" (3s) ---
    # Intelligence : On coupe 0.3s au début pour supprimer le silence de prise
    # On ajoute un zoom de 10% pour changer d'échelle (effet de caméra pro)
    os.system(f"ffmpeg -ss 0.3 -i r1.mp4 -t 3.0 -vf \"{vf_base},scale=1.1*iw:-1,crop=iw/1.1:ih/1.1\" -c:v libx264 -preset ultrafast c.mp4")

    # --- ÉTAPE C : LA PUNCHLINE (2.5s) ---
    # On finit sur un plan large avec un flash blanc au raccord
    os.system(f"ffmpeg -i r2.mp4 -t 2.5 -vf \"{vf_base},fade=t=in:st=0:d=0.2:color=white\" -c:v libx264 -preset ultrafast p.mp4")

    # 3. ASSEMBLAGE FINAL
    with open("list.txt", "w") as f:
        for m in ["h.mp4", "c.mp4", "p.mp4"]: f.write(f"file '{m}'\n")
    
    # Encodage final compatible 100% avec ton téléphone
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p output.mp4")
    
