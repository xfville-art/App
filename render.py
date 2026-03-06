import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # Extraction des vidéos
    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"v{i}.mp4"
        with open(name, "wb") as fout: fout.write(base64.b64decode(v['data']))
        files.append(name)

    # Montage (Simple concat pour éviter les erreurs)
    with open("list.txt", "w") as f:
        for m in files: f.write(f"file '{m}'\n")
    
    subprocess.run("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4", shell=True)

    # Encodage pour l'application mobile
    if os.path.exists("output.mp4"):
        with open("output.mp4", "rb") as f:
            res_b64 = base64.b64encode(f.read()).decode()
        with open("result.json", "w") as f:
            json.dump({"video": res_b64}, f)
        print("Fichier result.json créé avec succès")

if __name__ == "__main__":
    start()
