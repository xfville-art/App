import json, base64, os, subprocess

def start():
    # 1. Chargement sécurisé
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable")
        return
    
    with open('p.json', 'r') as f:
        data = json.load(f)

    # 2. Extraction des clips (r0.mp4, r1.mp4, r2.mp4)
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        print(f"Clip {i} extrait")

    # 3. Montage intelligent et robuste
    # On définit un format vertical standard 720p pour éviter de saturer le serveur
    vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setdar=9/16"

    # Hook / Core / Punchline avec des coupures propres
    os.system(f"ffmpeg -i r0.mp4 -t 2 -vf '{vf}' -c:v libx264 -preset superfast h.mp4")
    os.system(f"ffmpeg -i r1.mp4 -t 3 -vf '{vf}' -c:v libx264 -preset superfast c.mp4")
    os.system(f"ffmpeg -i r2.mp4 -t 3 -vf '{vf}' -c:v libx264 -preset superfast p.mp4")

    # 4. Fusion finale
    with open("list.txt", "w") as f:
        f.write("file 'h.mp4'\nfile 'c.mp4'\nfile 'p.mp4'")
    
    # Commande de concaténation ultra-compatible
    subprocess.run("ffmpeg -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p -movflags +faststart output.mp4", shell=True)
    
    if os.path.exists("output.mp4"):
        print("SUCCÈS : output.mp4 créé avec succès.")
    else:
        print("ÉCHEC : Le fichier n'a pas été généré.")

if __name__ == "__main__":
    start()
