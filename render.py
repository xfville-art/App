import json, base64, os, subprocess

def get_duration(file):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {file}"
    return float(subprocess.check_output(cmd, shell=True))

def start():
    print("--- VIRACUT V8 : MONTAGE PRO ---")
    if not os.path.exists('p.json'): return

    with open('p.json', 'r') as f:
        data = json.load(f)

    # 1. Extraction
    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"raw_{i}.mp4"
        with open(name, "wb") as fout: fout.write(base64.b64decode(v['data']))
        files.append(name)

    if len(files) < 2: return

    # 2. Montage Cinématique
    vf = "eq=contrast=1.1:saturation=1.3"
    os.system(f"ffmpeg -i {files[0]} -t 2 -vf {vf} -c:v libx264 -preset superfast hook.mp4")
    
    dur = get_duration(files[1])
    os.system(f"ffmpeg -ss {max(0, dur/2-2)} -i {files[1]} -t 4 -vf {vf} -c:v libx264 -preset superfast core.mp4")
    
    dur_last = get_duration(files[-1])
    os.system(f"ffmpeg -ss {max(0, dur_last-3)} -i {files[-1]} -t 3 -vf {vf} -c:v libx264 -preset superfast punch.mp4")

    # 3. Fusion Finale
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "core.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p output.mp4")

    # 4. CRUCIAL : Envoi du résultat encodé pour l'application mobile
    with open("output.mp4", "rb") as f:
        res_b64 = base64.b64encode(f.read()).decode()
    
    # Ce fichier est celui que l'App attend pour lancer le téléchargement
    with open("result.json", "w") as f:
        json.dump({"video": res_b64}, f)
    
    print("TERMINÉ : result.json créé pour l'App.")

if __name__ == "__main__":
    start()
