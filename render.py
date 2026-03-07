import json, base64, os, subprocess

def update_progress(text):
    with open("progress.txt", "w") as f:
        f.write(text)

def main():
    # 1. Vérification sécurisée du fichier p.json
    if not os.path.exists('p.json'):
        update_progress("Erreur: p.json absent")
        return

    try:
        with open('p.json', 'r') as f:
            raw_data = json.load(f)
        
        # On gère les deux cas : JSON direct ou JSON encapsulé dans 'content'
        if 'content' in raw_data:
            data_str = base64.b64decode(raw_data['content']).decode('utf-8')
            data = json.loads(data_str)
        else:
            data = raw_data # Si envoyé sans base64 par erreur
            
        videos = data.get('videos', [])
    except Exception as e:
        update_progress(f"Erreur structure: {str(e)}")
        return

    processed = []
    
    # 2. Encodage des segments
    for i, v in enumerate(videos):
        in_f, out_f = f"in_{i}.mp4", f"seg_{i}.ts"
        update_progress(f"Rendu Clip {i+1}/{len(videos)}...")
        
        with open(in_f, "wb") as f:
            f.write(base64.b64decode(v['data']))
        
        # Filtre texte et encodage ultra-rapide (4.7x speed dans tes logs)
        cmd = [
            'ffmpeg', '-y', '-i', in_f,
            '-vf', f"scale=720:1280,drawtext=text='{v.get('text','')}':fontcolor=yellow:fontsize=50:x=(w-text_w)/2:y=(h-text_h)/2",
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f
        ]
        subprocess.run(cmd)
        processed.append(out_f)

    # 3. Création du fichier final output.mp4 [Indispensable pour l'étape 6 de tes logs]
    if processed:
        with open('concat.txt', 'w') as f:
            for n in processed: f.write(f"file '{n}'\n")
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("TERMINÉ")
        print("output.mp4 créé avec succès.")

if __name__ == "__main__":
    main()
