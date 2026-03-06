import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction rapide
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout:
            fout.write(base64.b64decode(v['data']))

    # 2. Montage Propre (Sans effets lourds pour éviter le crash)
    # On retaille juste en vertical 9:16 pour TikTok/Reels
    vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"

    # Hook (Clip 0) : Coupe à 2s
    os.system(f"ffmpeg -i r0.mp4 -t 2 -vf '{vf}' -c:v libx264 -preset superfast h.mp4")
    # Core (Clip 1) : Coupe à 4s
    os.system(f"ffmpeg -i r1.mp4 -t 4 -vf '{vf}' -c:v libx264 -preset superfast c.mp4")
    # Punchline (Clip 2) : Coupe à 3s
    os.system(f"ffmpeg -i r2.mp4 -t 3 -vf '{vf}' -c:v libx264 -preset superfast p.mp4")

    # 3. Assemblage Final
    with open("list.txt", "w") as f:
        for m in ["h.mp4", "c.mp4", "p.mp4"]: f.write(f"file '{m}'\n")
    
    # Création du fichier final output.mp4
    subprocess.run("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4", shell=True)

if __name__ == "__main__":
    start()
