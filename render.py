import json, base64, os, subprocess

def update_progress(text):
    with open("progress.txt", "w") as f:
        f.write(text)

def main():
    # 1. Vérification du fichier de données
    if not os.path.exists('p.json'):
        update_progress("Erreur: p.json manquant")
        return

    try:
        with open('p.json', 'r') as f:
            raw_data = json.load(f)
        
        # Correction KeyError: on récupère 'content' de manière sécurisée
        encoded_content = raw_data.get('content', '')
        if not encoded_content:
            update_progress("Erreur: JSON vide")
            return
            
        data = json.loads(base64.b64decode(encoded_content).decode('utf-8'))
        videos = data.get('videos', [])
    except Exception as e:
        update_progress(f"Erreur décodage: {str(e)}")
        return

    processed_files = []
    
    # 2. Traitement des clips
    for i, v in enumerate(videos):
        in_file = f"input_{i}.mp4"
        out_file = f"segment_{i}.ts"
        
        update_progress(f"Traitement clip {i+1}/{len(videos)}...")
        
        # Sauvegarde du média
        with open(in_file, "wb") as f:
            f.write(base64.b64decode(v['data']))
        
        # Encodage (Paramètres optimisés selon tes logs)
        cmd = [
            'ffmpeg', '-y', '-i', in_file,
            '-vf', f"scale=720:1280,drawtext=text='{v.get('text','')}':fontcolor=yellow:fontsize=50:x=(w-text_w)/2:y=(h-text_h)/2",
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', out_file
        ]
        subprocess.run(cmd)
        processed_files.append(out_file)

    # 3. Fusion finale (Génère output.mp4 attendu par GitHub)
    if processed_files:
        with open('concat_list.txt', 'w') as f:
            for f_name in processed_files:
                f.write(f"file '{f_name}'\n")
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")
        print("Rendu terminé: output.mp4 généré.")

if __name__ == "__main__":
    main()
