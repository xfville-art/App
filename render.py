import json
import base64
import os
import subprocess

def get_duration(file):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {file}"
    return float(subprocess.check_output(cmd, shell=True))

def start():
    print("--- DÉMARRAGE DU MONTAGE VIRACUT V6 ---")
    
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable")
        return

    with open('p.json', 'r') as f:
        data = json.load(f)

    # 1. Extraction des fichiers
    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"raw_{i}.mp4"
        with open(name, "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        files.append(name)

    if len(files) < 2:
        print("Besoin d'au moins 2 vidéos pour un montage dynamique.")
        if files: os.system(f"ffmpeg -i {files[0]} -y output.mp4")
        return

    # 2. Découpage dynamique (Hook / Core / Punchline)
    print("Découpage des séquences...")
    
    # HOOK : 2 sec du début de la vidéo 1
    os.system(f"ffmpeg -i {files[0]} -t 2 -c:v libx264 -an hook.mp4")
    
    # CORE : 5 sec du milieu de la vidéo 2
    dur = get_duration(files[1])
    start_core = max(0, (dur / 2) - 2.5)
    os.system(f"ffmpeg -ss {start_core} -i {files[1]} -t 5 -c:v libx264 -an core.mp4")
    
    # PUNCHLINE : 3 sec de la fin de la dernière vidéo
    last_vid = files[-1]
    dur_last = get_duration(last_vid)
    os.system(f"ffmpeg -ss {dur_last - 3} -i {last_vid} -t 3 -c:v libx264 -an punch.mp4")

    # 3. Assemblage final avec transitions
    print("Assemblage final...")
    with open("list.txt", "w") as f:
        f.write("file 'hook.mp4'\nfile 'core.mp4'\nfile 'punch.mp4'")
    
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4")
    print("Fichier output.mp4 généré avec succès !")

if __name__ == "__main__":
    start()
