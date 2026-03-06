import json, base64, os, subprocess

def get_duration(file):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {file}"
    return float(subprocess.check_output(cmd, shell=True))

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"raw_{i}.mp4"
        with open(name, "wb") as fout: fout.write(base64.b64decode(v['data']))
        files.append(name)

    if len(files) < 3: return

    # --- CONFIGURATION VIRALE ---
    # Filtre : Amélioration des détails (unsharp) + Couleurs (saturation)
    vf = "unsharp=3:3:1.5:3:3:0.5,eq=saturation=1.3:contrast=1.1"

    # 1. HOOK (Accroche) : On prend les 2 premières secondes avec un zoom "Shake"
    os.system(f"ffmpeg -i {files[0]} -t 2 -vf \"{vf},zoompan=z='min(zoom+0.0015,1.5)':d=50:s=1080x1920\" -c:v libx264 -crf 18 -preset superfast v1.mp4")

    # 2. CORE (Le fond) : On cherche une partie stable au milieu
    d2 = get_duration(files[1])
    os.system(f"ffmpeg -ss {d2/4} -i {files[1]} -t 4 -vf \"{vf}\" -c:v libx264 -crf 18 -preset superfast v2.mp4")

    # 3. PUNCHLINE (Le final) : On prend la fin avec un effet de ralentissement léger
    d3 = get_duration(files[2])
    os.system(f"ffmpeg -ss {max(0, d3-3)} -i {files[2]} -t 3 -vf \"{vf},setpts=1.2*PTS\" -c:v libx264 -crf 18 -preset superfast v3.mp4")

    # 4. RACCORDS INTELLIGENTS (Transitions Crossfade)
    # On utilise un script complexe pour fondre les vidéos ensemble
    filter_complex = (
        "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=1.5[v01];"
        "[v01][2:v]xfade=transition=fade:duration=0.5:offset=5.0[vfinal]"
    )
    
    # Commande de fusion avec transitions et mixage audio
    cmd = (
        f"ffmpeg -i v1.mp4 -i v2.mp4 -i v3.mp4 -filter_complex \"{filter_complex}\" "
        "-map \"[vfinal]\" -c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    os.system(cmd)
    print("Montage intelligent terminé.")

if __name__ == "__main__":
    start()
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
