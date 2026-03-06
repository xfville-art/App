import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction et Nettoyage
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout: fout.write(base64.b64decode(v['data']))

    # --- ÉTAPE A : LE HOOK "STOP-SCROLL" (1.2s) ---
    # Zoom violent + Saturation Max + Vitesse accélérée (x1.2)
    os.system("ffmpeg -i r0.mp4 -t 1.2 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setpts=0.8*PTS,unsharp=5:5:1.5,eq=saturation=1.7' -c:v libx264 -preset ultrafast hook.mp4")

    # --- ÉTAPE B : LE CORE "JUMP-CUTS" (3.5s) ---
    # On crée 2 micro-clips du milieu pour donner une impression de montage pro
    os.system("ffmpeg -i r1.mp4 -ss 0.5 -t 1.5 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=saturation=1.2' -c:v libx264 -preset ultrafast c1.mp4")
    os.system("ffmpeg -i r1.mp4 -ss 2.5 -t 2.0 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z=1.1:x=iw/4:y=ih/4:d=1:s=1080x1920' -c:v libx264 -preset ultrafast c2.mp4")

    # --- ÉTAPE C : LA PUNCHLINE "CINÉMATIQUE" (2.5s) ---
    # Ralenti léger (x1.2) + Vignette noire pour l'impact
    os.system("ffmpeg -i r2.mp4 -t 2.5 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setpts=1.2*PTS,vignette=PI/4,fade=t=in:st=0:d=0.3:color=white' -c:v libx264 -preset ultrafast punch.mp4")

    # --- 2. ASSEMBLAGE FINAL ---
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "c1.mp4", "c2.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    # On s'assure que le fichier final s'appelle bien output.mp4 pour l'Artifact
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4")
    
    # Backup pour ton App si jamais le bouton finit par marcher
    if os.path.exists("output.mp4"):
        with open("output.mp4", "rb") as f:
            res_b64 = base64.b64encode(f.read()).decode()
        with open("result.json", "w") as f:
            json.dump({"video": res_b64}, f)

if __name__ == "__main__":
    start()
