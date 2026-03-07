import json
import base64
import os
import subprocess

def main():
    # 1. Vérifier si le fichier p.json existe à la racine
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable.")
        exit(1)

    # 2. Charger les données directement
    # Note: Ton App HTML fait un btoa() du JSON, donc on décode une fois
    with open('p.json', 'r') as f:
        try:
            # On lit le fichier qui contient le b64 envoyé par l'App
            file_data = json.load(f)
            # Selon ton code JS: content: btoa(JSON.stringify({ videos, options }))
            raw_data = base64.b64decode(file_data['content'])
            data = json.loads(raw_data)
        except Exception as e:
            print(f"Erreur de lecture JSON/Base64 : {e}")
            exit(1)

    videos = data['videos']
    opt = data['options']
    
    print(f"Traitement de {len(videos)} clips...")

    # 3. Extraire les vidéos
    input_files = []
    for i, v in enumerate(videos):
        filename = f"clip_{i}.mp4"
        with open(filename, "wb") as f:
            f.write(base64.b64decode(v['data']))
        input_files.append(filename)

    # 4. Concaténation FFmpeg
    with open('inputs.txt', 'w') as f:
        for fname in input_files:
            f.write(f"file '{fname}'\n")

    res = opt['resolution'].replace('x', ':')
    
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', 'inputs.txt',
        '-vf', f"scale={res},fps={opt['fps']}",
        '-c:v', 'libx264', '-crf', str(opt['crf']),
        '-pix_fmt', 'yuv420p',
        'output.mp4'
    ]

    print("Démarrage du rendu...")
    subprocess.run(cmd, check=True)
    print("Succès : output.mp4 créé.")

if __name__ == "__main__":
    main()
