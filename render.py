import json
import base64
import os
import subprocess

def main():
    # 1. Vérifier la présence des données
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable.")
        exit(1)

    # 2. Lire et décoder le JSON
    try:
        with open('p.json', 'r') as f:
            # L'API GitHub stocke le contenu dans une clé 'content' en base64
            # Mais lors d'un 'checkout' dans une Action, on lit le fichier brut.
            # Ton App fait : btoa(JSON.stringify({videos, options}))
            raw_content = json.load(f)
            
            # On décode le contenu global envoyé par l'App
            decoded_data = json.loads(base64.b64decode(raw_content['content']))
            
            videos = decoded_data['videos']
            opt = decoded_data['options']
    except Exception as e:
        print(f"Erreur lors du décodage : {e}")
        exit(1)

    print(f"Traitement de {len(videos)} clips...")

    # 3. Extraire les fichiers vidéo temporaires
    input_list = []
    for i, v in enumerate(videos):
        fname = f"input_{i}.mp4"
        with open(fname, "wb") as vf:
            vf.write(base64.b64decode(v['data']))
        input_list.append(fname)

    # 4. Créer le fichier de concaténation pour FFmpeg
    with open('concat.txt', 'w') as f:
        for fname in input_list:
            f.write(f"file '{fname}'\n")

    # 5. Lancer FFmpeg
    # On adapte la résolution (ex: 720x1280 -> 720:1280)
    res = opt['resolution'].replace('x', ':').replace('×', ':')
    
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', 'concat.txt',
        '-vf', f"scale={res},fps={opt['fps']}",
        '-c:v', 'libx264', '-crf', str(opt['crf']),
        '-pix_fmt', 'yuv420p',
        'output.mp4'
    ]

    print("Exécution de FFmpeg...")
    subprocess.run(cmd, check=True)
    print("Rendu terminé : output.mp4 généré.")

if __name__ == "__main__":
    main()
            
