import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f:
        raw = json.load(f)
    
    # Décodage sécurisé pour éviter l'échec du rendu
    content = raw.get('content', raw)
    data = json.loads(base64.b64decode(content).decode('utf-8')) if isinstance(content, str) else content
    videos = data.get('videos', [])

    segments = []
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))

        # EFFETS VIRAUX : Zoom IA + Texte Animé qui pulse
        txt = v.get('text','').upper().replace("'", "\\'")
        filter_str = (
            f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
            f"zoompan=z='zoom+0.0015':d=125:s=720x1280," # Zoom lent et constant
            f"drawtext=text='{txt}':fontcolor=yellow:fontsize='70+20*sin(2*3.14*t/0.6)':" # Texte pulsé
            f"x=(w-text_w)/2:y=(h-text_h)/2+250:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"borderw=6:bordercolor=black" # Contour noir pour la lisibilité
        )

        cmd = ['ffmpeg', '-y', '-i', in_f, '-vf', filter_str, '-c:v', 'libx264', '-preset', 'ultrafast', '-t', '5', out_f]
        if subprocess.run(cmd).returncode == 0:
            segments.append(out_f)

    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        # Fusion finale vers output.mp4
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])

if __name__ == "__main__": main()
