import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f:
        raw = json.load(f)
        data = json.loads(base64.b64decode(raw['content'])) if isinstance(raw, dict) and 'content' in raw else raw

    videos = data.get('videos', [])
    res_w, res_h = 720, 1280
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    processed = []

    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"o_{i}.ts"
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))

        # Analyse durée
        dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', in_f]).decode().strip() or 2.0)

        # --- FILTRE CINÉMA PRO ---
        # 1. Étalonnage (eq) + Zoom Progressif (zoompan)
        # 2. Bandes noires Cinemascope
        vf = (f"scale=1280:2276,zoompan=z='min(zoom+0.0015,1.5)':d={int(dur*25)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={res_w}x{res_h},"
              f"eq=brightness=0.03:contrast=1.3:saturation=1.5," 
              f"vignette='PI/4',"
              f"drawbox=y=0:color=black:width=iw:height=ih/10:t=fill,"
              f"drawbox=y=ih-ih/10:color=black:width=iw:height=ih/10:t=fill")
        
        # --- TEXTE ANIMÉ STYLE "HORMOZI" ---
        text = v.get('text', '').strip().upper()
        if text:
            words = text.split()
            w_dur = dur / len(words)
            for idx, w in enumerate(words):
                start, end = idx * w_dur, (idx + 1) * w_dur
                color = "yellow" if idx % 2 == 0 else "white" # Alternance pro
                
                vf += (f",drawtext=fontfile='{font}':text='{w}':fontcolor={color}:fontsize=90:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2+100:borderw=5:bordercolor=black@0.8:"
                       f"shadowcolor=black@0.6:shadowx=6:shadowy=6:"
                       f"enable='between(t,{start},{end})'")

        # Transition Flash discret
        vf += ",drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.08)'"

        subprocess.run(['ffmpeg', '-y', '-i', in_f, '-vf', vf, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', out_f], check=True)
        processed.append(out_f)

    # Fusion finale
    with open('list.txt', 'w') as f:
        for n in processed: f.write(f"file '{n}'\n")
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', 'output.mp4'], check=True)

if __name__ == "__main__":
    main()
