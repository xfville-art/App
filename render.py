import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f:
        raw = json.load(f)
    
    # Décodage robuste pour éviter l'erreur de l'action #144
    content = raw.get('content', raw)
    data = json.loads(base64.b64decode(content).decode('utf-8')) if isinstance(content, str) else content
    videos = data.get('videos', [])

    segments = []
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))

        # IA FX : SHAKE + ZOOM + TEXTE ANIMÉ (Battement de coeur)
        txt = v.get('text','').upper().replace("'", "\\'")
        filter_str = (
            f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
            f"zoompan=z='zoom+0.003+0.01*sin(t*10)':d=1:s=720x1280," # Tremblement de caméra IA
            f"drawtext=text='{txt}':fontcolor=white:fontsize='(80+20*sin(t*12))':" # Texte qui pulse
            f"x=(w-text_w)/2:y=(h-text_h)/2:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"box=1:boxcolor=red@0.8:boxborderw=20," # Fond rouge flash pour l'impact
            f"vignette='PI/4+PI/4*sin(t*5)'" # Effet de flash sur les bords
        )

        cmd = ['ffmpeg', '-y', '-i', in_f, '-vf', filter_str, '-c:v', 'libx264', '-preset', 'ultrafast', '-t', '4', out_f]
        if subprocess.run(cmd).returncode == 0:
            segments.append(out_f)

    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        # Génération finale du fichier output.mp4
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
