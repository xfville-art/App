import json, base64, os, subprocess

def start():
    print("--- DEBUT DU RENDU ---")
    if not os.path.exists('p.json'):
        print("Erreur: p.json introuvable")
        return

    with open('p.json', 'r') as f:
        data = json.load(f)

    # 1. Extraction des clips envoyés par le téléphone
    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"v{i}.mp4"
        with open(name, "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        files.append(name)

    # 2. Montage simple (on colle les vidéos bout à bout)
    with open("list.txt", "w") as f:
        for m in files: f.write(f"file '{m}'\n")
    
    # On crée le fichier final output.mp4
    subprocess.run("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4", shell=True)

    # 3. VERIFICATION ET ENVOI VERS L'APP
    if os.path.exists("output.mp4"):
        with open("output.mp4", "rb") as f:
            res_b64 = base64.b64encode(f.read()).decode()
        
        # On crée le fichier result.json que l'app surveille
        result_data = {"video": res_b64}
        with open("result.json", "w") as f:
            json.dump(result_data, f)
        print("SUCCÈS: result.json est prêt.")
    else:
        print("ERREUR: Le montage a échoué.")

if __name__ == "__main__":
    start()
