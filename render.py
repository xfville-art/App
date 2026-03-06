import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction des clips bruts
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout:
            fout.write(base64.b64decode(v['data']))

    # Filtre de rendu : Netteté + Couleurs Vibrantes
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:1.0,eq=saturation=1.4"

    # 2. MONTAGE RYTHMÉ (On retire 0.2s de silence au début de chaque clip)
    # HOOK (Clip 0) : Accroche rapide de 1.5s avec zoom
    os.system(f"ffmpeg -ss 0.2 -i r0.mp4 -t 1.5 -vf '{vf},zoompan=z=1.1:d=1:s=1080x1920' -c:v libx264 -preset ultrafast h.mp4")
    
    # CORE (Clip 1) : Le dialogue principal de 3s
    os.system(f"ffmpeg -ss 0.2 -i r1.mp4 -t 3.0 -vf '{vf}' -c:v libx264 -preset ultrafast c.mp4")
    
    # PUNCHLINE (Clip 2) : La fin de 2.5s avec flash d'impact
    os.system(f"ffmpeg -ss 0.1 -i r2.mp4 -t 2.5 -vf '{vf},fade=t=in:st=0:d=0.2:color=white' -c:v libx264 -preset ultrafast p.mp4")

    # 3. FUSION FINALE
    with open("list.txt", "w") as f:
        for m in ["h.mp4", "c.mp4", "p.mp4"]: f.write(f"file '{m}'\n")
    
    # Création du fichier output.mp4 attendu par le Workflow
    subprocess.run("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4", shell=True)
    
    # Sauvegarde du résultat en JSON pour l'App
    if os.path.exists("output.mp4"):
        with open("output.mp4", "rb") as f:
            res_b64 = base64.b64encode(f.read()).decode()
        with open("result.json", "w") as f:
            json.dump({"video": res_b64}, f)

if __name__ == "__main__":
    start()
