import json, base64, os, subprocess

def get_duration(file):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {file}"
    return float(subprocess.check_output(cmd, shell=True))

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction et nettoyage
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout: fout.write(base64.b64decode(v['data']))

    # Filtre Pro : Netteté + Saturation + Recadrage vertical strict
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:1.0,eq=saturation=1.3"

    # 2. MONTAGE INTELLIGENT (Coupures basées sur la durée réelle)
    # Clip 1 (Hook) : On prend les 2 premières secondes
    os.system(f"ffmpeg -i r0.mp4 -t 2 -vf \"{vf},zoompan=z='min(zoom+0.0015,1.5)':d=1:s=1080x1920\" -c:v libx264 -preset ultrafast h.mp4")
    
    # Clip 2 (Core) : On prend le milieu
    d2 = get_duration("r1.mp4")
    os.system(f"ffmpeg -ss {d2/4} -i r1.mp4 -t 4 -vf \"{vf}\" -c:v libx264 -preset ultrafast c.mp4")
    
    # Clip 3 (Punchline) : On prend les 3 dernières secondes
    d3 = get_duration("r2.mp4")
    os.system(f"ffmpeg -ss {max(0, d3-3)} -i r2.mp4 -t 3 -vf \"{vf},fade=t=in:st=0:d=0.3:color=white\" -c:v libx264 -preset ultrafast p.mp4")

    # 3. ASSEMBLAGE FINAL
    with open("list.txt", "w") as f:
        for m in ["h.mp4", "c.mp4", "p.mp4"]: f.write(f"file '{m}'\n")
    
    # Génération du fichier final attendu par GitHub
    subprocess.run("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4", shell=True)
    
    # Sauvegarde pour ton App
    if os.path.exists("output.mp4"):
        with open("output.mp4", "rb") as f:
            res_b64 = base64.b64encode(f.read()).decode()
        with open("result.json", "w") as f:
            json.dump({"video": res_b64}, f)

if __name__ == "__main__":
    start()
