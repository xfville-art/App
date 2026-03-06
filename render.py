import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. EXTRACTION RAPIDE (Sauvegarde des 3 clips)
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout: fout.write(base64.b64decode(v['data']))

    # --- CONFIGURATION ÉLITE ---
    # Filtre de base : Netteté (unsharp) + Saturation boostée (1.4)
    vf_base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:1.0:5:5:0.5,eq=saturation=1.4"

    # --- ÉTAPE A : LE HOOK "STOP-SCROLL" (1.5s) ---
    # Un zoom progressif violent pour capter l’œil immédiatement
    os.system(f"ffmpeg -i r0.mp4 -t 1.5 -vf \"{vf_base},zoompan=z='min(zoom+0.005,1.5)':d=1:s=1080x1920\" -c:v libx264 -preset ultrafast hook.mp4")

    # --- ÉTAPE B : LE CORE "JUMP-CUTS" (3.5s) ---
    # On coupe 0.5s au début pour supprimer le "blanc" et on booste le rythme
    os.system(f"ffmpeg -ss 0.5 -i r1.mp4 -t 3.5 -vf \"{vf_base}\" -c:v libx264 -preset ultrafast core.mp4")

    # --- ÉTAPE C : LA PUNCHLINE "IMPACT" (2.5s) ---
    # Un flash blanc au raccord pour marquer la fin de façon pro
    os.system(f"ffmpeg -i r2.mp4 -t 2.5 -vf \"{vf_base},fade=t=in:st=0:d=0.2:color=white\" -c:v libx264 -preset ultrafast punch.mp4")

    # 3. ASSEMBLAGE FINAL AVEC RACCORDS MOINS BRUTAUX
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "core.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    # On génère output.mp4 pour tes Artifacts
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4")
