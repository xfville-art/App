import json
import base64
import os
import subprocess

def main():
    # 1. Vérification du fichier de données
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable. L'App n'a pas envoyé les données.")
        exit(1)

    # 2. Lecture et décodage
    try:
        with open('p.json', 'r') as f:
            # L'API GitHub renvoie le contenu dans un dictionnaire sous la clé 'content'
            raw_github_data = json.load(f)
            # Décodage du Base64 global (envoyé par ton App-2.html)
            decoded_json = base64.b64decode(raw_github_data['content'])
            data = json.loads(decoded_json)
    except Exception as e:
        print(f"Erreur de décodage : {e}")
        exit(1)

    videos = data['videos']
    opt = data['options']
    
    print(f"Traitement de {len(videos)} clips...")

    # 3. Extraction des fichiers vidéos temporaires
    input_files = []
    for i, v in enumerate(videos):
        fname = f"clip_{i}.mp4"
        with open(fname, "wb") as f:
            f.write(base64.b64decode(v['data']))
        input_files.append(fname)

    # 4. Préparation de la fusion FFmpeg
    # On crée une liste de fichiers pour FFmpeg
    with open('list.txt', 'w') as f:
        for name in input_files:
            f.write(f"file '{name}'\n")

    # Formatage de la résolution (ex: 720x1280 -> 720:1280)
    resolution = opt['resolution'].replace('x', ':').replace('×', ':')
    
    # Commande FFmpeg
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', 'list.txt',
        '-vf', f"scale={resolution},fps={opt['fps']}",
        '-c:v', 'libx264',
        '-crf', str(opt['crf']),
        '-pix_fmt', 'yuv420p',
        'output.mp4'
    ]

    # 5. Exécution
    print("Démarrage de FFmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("Erreur FFmpeg :", result.stderr)
        exit(1)
    
    print("Succès ! Fichier output.mp4 prêt.")

if __name__ == "__main__":
    main()
    
