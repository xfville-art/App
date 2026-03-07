import json, base64, os, subprocess

def update_progress(text):
    with open("progress.txt", "w") as f:
        f.write(text)

def main():
    if not os.path.exists('p.json'): return
    try:
        with open('p.json', 'r') as f:
            raw = json.load(f)
        content = raw.get('content', raw)
        data = json.loads(base64.b64decode(content).decode('utf-8')) if isinstance(content, str) else content
        videos = data.get('videos', [])
    except: return

    segments = []
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        update_progress(f"Editing Viral Clip {i+1}...")
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))

        # EFFET VIRAL : Zoom progressif + Texte Punchy + Flash de début
        # On utilise 'zoompan' pour créer du mouvement même sur les images fixes
        txt = v.get('text','').upper().replace("'", "\\'")
        filter_str = (
            f"zoompan=z='min(zoom+0.0015,1.5)':d=1:s=720x1280," # Zoom lent continu
            f"drawtext=text='{txt}':fontcolor=yellow:fontsize='85':"
            f"x=(w-text_w)/2:y=(h-text_h)/2+100*sin(2*3.14*t):" # Rebond plus sec
            f"box=1:boxcolor=black@0.5:boxborderw=10," # Fond noir derrière le texte pour la lisibilité
            f"fade=t=in:st=0:d=0.2:color=white" # Flash blanc de 0.2s au début
        )

        cmd = [
            'ffmpeg', '-y', '-i', in_f,
            '-vf', filter_str,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-t', '5', out_f
        ]
        subprocess.run(cmd)
        segments.append(out_f)

    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")

if __name__ == "__main__": main()
