import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction et formatage vertical (9:16)
    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"raw_{i}.mp4"
        with open(name, "wb") as fout: fout.write(base64.b64decode(v['data']))
        # Normalisation immédiate pour TikTok/Reels
        os.system(f"ffmpeg -i {name} -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920' -c:v libx264 -preset ultrafast clip_{i}.mp4")
        files.append(f"clip_{i}.mp4")

    if len(files) < 3: return

    # --- ÉTAPE A : LE HOOK (Accroche - 2 secondes) ---
    # Ajout d'un zoom dynamique pour capter l'attention
    os.system(f"ffmpeg -i {files[0]} -t 2 -vf \"zoompan=z='min(zoom+0.002,1.5)':d=1:s=1080x1920\" -c:v libx264 hook.mp4")

    # --- ÉTAPE B : LE CORE (Contenu - 4 secondes) ---
    # Amélioration des couleurs et de la netteté
    os.system(f"ffmpeg -i {files[1]} -ss 1 -t 4 -vf \"unsharp=5:5:1.0,eq=saturation=1.3\" -c:v libx264 core.mp4")

    # --- ÉTAPE C : LA PUNCHLINE (Conclusion - 3 secondes) ---
    # Effet de fondu au blanc pour une fin "punchy"
    os.system(f"ffmpeg -i {files[2]} -t 3 -vf \"fade=t=in:st=0:d=0.3:color=white\" -c:v libx264 punch.mp4")

    # 2. ASSEMBLAGE FINAL (Raccords fluides)
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "core.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    # Création du fichier final
    subprocess.run("ffmpeg -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p output.mp4", shell=True)
    
    # Encodage pour l'App (en cas de besoin)
    if os.path.exists("output.mp4"):
        with open("output.mp4", "rb") as f:
            res_b64 = base64.b64encode(f.read()).decode()
        with open("result.json", "w") as f:
            json.dump({"video": res_b64}, f)

if __name__ == "__main__":
    start()
