import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction et Normalisation
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout: fout.write(base64.b64decode(v['data']))

    # --- STRATÉGIE DE COUPE SUR DIALOGUE ---
    # On utilise 'silencedetect' pour identifier les pauses et couper proprement
    # Hook (Clip 1) : On garde l'intro jusqu'au premier silence
    os.system("ffmpeg -i r0.mp4 -af silencedetect=n=-30dB:d=0.1 -f null - 2> vol.txt")
    # On force une coupe propre à 1.8s si le silence n'est pas détecté pour éviter le bug Action #62
    os.system("ffmpeg -i r0.mp4 -t 1.8 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:1.0' -c:v libx264 -preset ultrafast hook.mp4")

    # --- CORE (Clip 2) : Match Cut (Coupe sur le mouvement/parole) ---
    # On enlève 0.5s au début pour supprimer le moment où tu lances l'enregistrement
    os.system("ffmpeg -ss 0.5 -i r1.mp4 -t 3.5 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=saturation=1.2' -c:v libx264 -preset ultrafast core.mp4")

    # --- PUNCHLINE (Clip 3) : L'Impact Final ---
    # On finit sur une note forte, recalée pour éviter les blancs de fin
    os.system("ffmpeg -i r2.mp4 -t 2.5 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fade=t=in:st=0:d=0.2:color=white' -c:v libx264 -preset ultrafast punch.mp4")

    # 2. ASSEMBLAGE SANS SAUT D'IMAGE
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "core.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    # On génère le fichier final pour les Artifacts
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4")
