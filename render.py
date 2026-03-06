import json, base64, os, subprocess

def get_duration(file):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {file}"
    return float(subprocess.check_output(cmd, shell=True))

def start():
    print("--- VIRACUT ENGINE V7 : CINEMATIC ---")
    if not os.path.exists('p.json'): return

    with open('p.json', 'r') as f:
        data = json.load(f)

    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"raw_{i}.mp4"
        with open(name, "wb") as fout: fout.write(base64.b64decode(v['data']))
        files.append(name)

    if len(files) < 2: return

    # Filtre Cinématique : Contraste +1.1, Saturation +1.2
    vf = "eq=contrast=1.1:saturation=1.2"

    # HOOK (2s) / CORE (5s) / PUNCHLINE (3s)
    os.system(f"ffmpeg -i {files[0]} -t 2 -vf {vf} -c:v libx264 -an hook.mp4")
    
    dur = get_duration(files[1])
    os.system(f"ffmpeg -ss {max(0, dur/2-2.5)} -i {files[1]} -t 5 -vf {vf} -c:v libx264 -an core.mp4")
    
    dur_last = get_duration(files[-1])
    os.system(f"ffmpeg -ss {dur_last-3} -i {files[-1]} -t 3 -vf {vf} -c:v libx264 -an punch.mp4")

    # Assemblage
    with open("list.txt", "w") as f: f.write("file 'hook.mp4'\nfile 'core.mp4'\nfile 'punch.mp4'")
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4")
    
    # Encodage du résultat pour le renvoyer à l'app
    with open("output.mp4", "rb") as f:
        res_b64 = base64.b64encode(f.read()).decode()
    
    # On stocke le résultat dans un fichier JSON que l'App pourra lire
    with open("result.json", "w") as f:
        json.dump({"video": res_b64}, f)

if __name__ == "__main__":
    start()
