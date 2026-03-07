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
        
        # Gestion flexible du contenu (direct ou encapsulé)
        content = raw.get('content', raw) 
        if isinstance(content, str):
            data = json.loads(base64.b64decode(content).decode('utf-8'))
        else:
            data = content
            
        videos = data.get('videos', [])
    except Exception as e:
        update_progress(f"Erreur décodage: {str(e)}")
        return

    segments = []
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        update_progress(f"Rendu Clip {i+1}/{len(videos)}...")

        with open(in_f, "wb") as f:
            f.write(base64.b64decode(v['data']))

        # FILTRE CORRIGÉ : Utilisation de 3.14159 au lieu de pi
        # Animation : Taille (battement) et position Y (oscillation)
        txt = v.get('text','').replace("'", "\\'")
        filter_str = (
            f"scale=720:1280,"
            f"drawtext=text='{txt}':fontcolor=yellow:fontsize='70+15*sin(2*3.14159*t/3)':"
            f"x=(w-text_w)/2:y=(h-text_h)/2+25*cos(2*3.14159*t/2):"
            f"shadowcolor=black:shadowx=4:shadowy=4"
        )

        cmd = [
            'ffmpeg', '-y', '-i', in_f,
            '-vf', filter_str,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f
        ]
        
        result = subprocess.run(cmd)
        if result.returncode == 0:
            segments.append(out_f)
        else:
            update_progress(f"Erreur FFmpeg sur clip {i}")

    # Fusion finale si des segments existent
    if segments:
        update_progress("Fusion finale...")
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")
    else:
        update_progress("ECHEC: Aucun segment produit")

if __name__ == "__main__":
    main()
