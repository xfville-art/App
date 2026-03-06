import json, base64, os, subprocess

def get_duration(file):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {file}"
    return float(subprocess.check_output(cmd, shell=True))

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction des 3 clips
    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"raw_{i}.mp4"
        with open(name, "wb") as fout: fout.write(base64.b64decode(v['data']))
        files.append(name)

    if len(files) < 3:
        print("Erreur : Il faut 3 clips pour le montage Viral.")
        return

    # 2. Paramètres visuels (Couleurs vibrantes + Contraste)
    vf_base = "eq=contrast=1.1:saturation=1.5"

    # --- ÉTAPE A : LE HOOK (Accroche rapide de 1.5s) ---
    # On prend le début du premier clip avec un zoom progressif
    os.system(f"ffmpeg -i {files[0]} -t 1.5 -vf \"{vf_base},zoompan=z='zoom+0.002':d=37.5:s=1080x1920\" -c:v libx264 -preset superfast hook.mp4")

    # --- ÉTAPE B : LE CORE (Le cœur du sujet 4s) ---
    # On prend le milieu du deuxième clip
    dur = get_duration(files[1])
    start_core = max(0, dur/2 - 2)
    os.system(f"ffmpeg -ss {start_core} -i {files[1]} -t 4 -vf \"{vf_base}\" -c:v libx264 -preset superfast core.mp4")

    # --- ÉTAPE C : LA PUNCHLINE (La conclusion 2.5s) ---
    # On prend la fin du dernier clip avec un léger flash blanc au début
    dur_last = get_duration(files[-1])
    start_punch = max(0, dur_last - 2.5)
    os.system(f"ffmpeg -ss {start_punch} -i {files[-1]} -t 2.5 -vf \"{vf_base},fade=t=in:st=0:d=0.2:color=white\" -c:v libx264 -preset superfast punch.mp4")

    # 3. ASSEMBLAGE FINAL
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "core.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p -crf 23 output.mp4")
    print("Montage Viral terminé.")

if __name__ == "__main__":
    start()
