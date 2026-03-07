import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f:
        raw = json.load(f)
    
    # Sécurité pour éviter le KeyError: 'content'
    content = raw.get('content', raw)
    data = json.loads(base64.b64decode(content).decode('utf-8')) if isinstance(content, str) else content
    videos = data.get('videos', [])

    segments = []
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))

        # IA ANIMATION : Zoom avant lent + Texte qui pulse (grossit/rétrécit)
        txt = v.get('text','').upper().replace("'", "\\'")
        filter_str = (
            f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
            f"zoompan=z='zoom+0.002':d=125:s=720x1280," # Zoom constant
            f"drawtext=text='{txt}':fontcolor=yellow:fontsize='80+20*sin(2*3.14*t/0.5)':" # Pulse IA
            f"x=(w-text_w)/2:y=(h-text_h)/2:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"borderw=8:bordercolor=black"
        )

        cmd = ['ffmpeg', '-y', '-i', in_f, '-vf', filter_str, '-c:v', 'libx264', '-preset', 'ultrafast', '-t', '5', out_f]
        if subprocess.run(cmd).returncode == 0: segments.append(out_f)

    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        # Fusion et création du fichier final
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
