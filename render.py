import json, base64, os, subprocess

def update_progress(text):
    with open("progress.txt", "w") as f:
        f.write(text)

def main():
    if not os.path.exists('p.json'): return
    try:
        with open('p.json', 'r') as f:
            raw = json.load(f)
        # Correction du plantage : on lit 'content' de manière sécurisée
        content = raw.get('content', raw)
        data = json.loads(base64.b64decode(content).decode('utf-8')) if isinstance(content, str) else content
        videos = data.get('videos', [])
    except: return

    segments = []
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        update_progress(f"Viral Edit Clip {i+1}...")
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))

        # FILTRE VIRAL : Zoom progressif + Secousse + Texte Punchy
        txt = v.get('text','').upper().replace("'", "\\'")
        filter_str = (
            f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
            f"zoompan=z='min(zoom+0.002,1.5)':d=1:s=720x1280," # Zoom dynamique
            f"drawtext=text='{txt}':fontcolor=white:fontsize=80:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"x=(w-text_w)/2:y=(h-text_h)/2+200:borderw=5:bordercolor=black," # Texte en bas avec bordure
            f"noise=alls=10:allf=t" # Petit grain "rétro" pour le style Crados
        )

        cmd = ['ffmpeg', '-y', '-i', in_f, '-vf', filter_str, '-c:v', 'libx264', '-preset', 'ultrafast', '-t', '5', out_f]
        if subprocess.run(cmd).returncode == 0:
            segments.append(out_f)

    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        # Fusion finale
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")

if __name__ == "__main__": main()
