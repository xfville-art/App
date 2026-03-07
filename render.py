import json
import base64
import os
import subprocess

def main():
    # 1. Vérifier si le fichier p.json existe
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable. L'interface HTML n'a pas envoyé les données.")
        exit(1)

    # 2. Charger les données (p.json contient du base64 selon ton code App-2.html)
    with open('p.json', 'r') as f:
        github_data = json.load(f)
        # Décodage du contenu envoyé par l'API GitHub
        raw_data = base64.b64decode(github_data['content'])
        data = json.loads(raw_data)

    videos = data['videos']
    opt = data['options']
    
    print(f"Traitement de {len(videos)} clips...")

    # 3. Extraire et sauvegarder les clips vidéo temporaires
    input_files = []
    for i, v in enumerate(videos):
        filename = f"clip_{i}.mp4"
        with open(filename, "wb") as f:
            f.write(base64.b64decode(v['data']))
        input_files.append(filename)

    # 4. Préparation de la commande FFmpeg (Fusion simple)
    # Note : On utilise la résolution et les FPS choisis dans ton interface
    res = opt['resolution'].replace('x', ':') # Conversion 720x1280 en format FFmpeg
    
    # Création du fichier de concaténation
    with open('inputs.txt', 'w') as f:
        for fname in input_files:
            f.write(f"file '{fname}'\n")

    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', 'inputs.txt',
        '-vf', f"scale={opt['resolution'].replace('x', ':')},fps={opt['fps']}",
        '-c:v', 'libx264',
        '-crf', str(opt['crf']),
        '-pix_fmt', 'yuv420p',
        'output.mp4'
    ]

    # 5. Exécution du rendu
    print("Démarrage du rendu FFmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("Erreur FFmpeg :", result.stderr)
        exit(1)
    
    print("Rendu terminé avec succès : output.mp4 généré.")

if __name__ == "__main__":
    main()
