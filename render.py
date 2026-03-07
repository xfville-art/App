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
        # On vérifie si les données sont encapsulées ou directes
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
        update_progress(f"Animation IA Clip {i+1}/{len(videos)}...")

        with open(in_f, "wb") as f:
            f.write(base64.b64decode(v['data']))

        # FILTRE DYNAMIQUE : Le texte "respire" (zoom) et "bouge" (rebond)
        # t = temps en secondes
        txt = v.get('text','').replace("'", "\\'")
        animation = (
            f"scale=720:1280,"
            f"drawtext=text='{txt}':fontcolor=yellow:fontsize='70+20*sin(2*pi*t/3)':"
            f"x=(w-text_w)/2:y=(h-text_h)/2+30*cos(2*pi*t/2):"
            f"shadowcolor=black:shadowx=4:shadowy=4"
        )

        cmd = [
            'ffmpeg', '-y', '-i', in_f,
            '-vf', animation,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f
        ]
        subprocess.run(cmd)
        segments.append(out_f)

    # Fusion finale pour générer output.mp4
    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")

if __name__ == "__main__":
    main()
