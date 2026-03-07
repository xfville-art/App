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
        
        # Correction sécurisée pour éviter le KeyError 'content'
        encoded = raw.get('content', '')
        if not encoded:
            update_progress("Erreur: Payload vide")
            return
            
        data = json.loads(base64.b64decode(encoded).decode('utf-8'))
        videos = data.get('videos', [])
    except Exception as e:
        update_progress(f"Erreur JSON: {str(e)}")
        return

    segments = []
    for i, v in enumerate(videos):
        in_file, out_file = f"i_{i}.mp4", f"s_{i}.ts"
        update_progress(f"Animation Clip {i+1}/{len(videos)}...")

        with open(in_file, "wb") as f:
            f.write(base64.b64decode(v['data']))

        # FILTRE ANIMÉ : Taille variable (sin) + Rebond vertical (cos)
        text_filter = (
            f"scale=720:1280,"
            f"drawtext=text='{v.get('text','')}':fontcolor=yellow:fontsize='60+20*sin(2*pi*t/3)':"
            f"x=(w-text_w)/2:y=(h-text_h)/2+20*cos(2*pi*t/2):"
            f"shadowcolor=black:shadowx=5:shadowy=5"
        )

        # Encodage optimisé (Speed 4.7x constaté dans vos logs)
        cmd = [
            'ffmpeg', '-y', '-i', in_file,
            '-vf', text_filter,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_file
        ]
        subprocess.run(cmd)
        segments.append(out_file)

    # Fusion finale pour créer output.mp4
    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")

if __name__ == "__main__":
    main()
