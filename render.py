import json, base64, os, subprocess

def update_progress(text):
    with open("progress.txt", "w") as f:
        f.write(text)

def main():
    if not os.path.exists('p.json'):
        update_progress("Erreur: p.json introuvable")
        return

    try:
        with open('p.json', 'r') as f:
            raw = json.load(f)
        
        # Correction du KeyError 'content'
        encoded = raw.get('content', '')
        if not encoded:
            update_progress("Erreur: Données vides")
            return
            
        data = json.loads(base64.b64decode(encoded).decode('utf-8'))
        videos = data.get('videos', [])
    except Exception as e:
        update_progress(f"Erreur JSON: {str(e)}")
        return

    segments = []
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        update_progress(f"Animation Clip {i+1}/{len(videos)}...")

        with open(in_f, "wb") as f:
            f.write(base64.b64decode(v['data']))

        # FILTRE IA ANIMÉ : 
        # fontsize : varie entre 50 et 80 (effet de battement)
        # y : mouvement de haut en bas de 20 pixels
        txt = v.get('text','').replace("'", "\\'")
        filter_str = (
            f"scale=720:1280,"
            f"drawtext=text='{txt}':fontcolor=yellow:fontsize='65+15*sin(2*pi*t/2)':"
            f"x=(w-text_w)/2:y=(h-text_h)/2+25*cos(2*pi*t/1.5):"
            f"shadowcolor=black:shadowx=4:shadowy=4"
        )

        cmd = [
            'ffmpeg', '-y', '-i', in_f,
            '-vf', filter_str,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f
        ]
        subprocess.run(cmd)
        segments.append(out_f)

    # Création du fichier final pour éviter l'erreur d'artéfact
    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")

if __name__ == "__main__":
    main()
