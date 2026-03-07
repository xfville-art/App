import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'):
        print("Erreur : p.json absent"); exit(1)

    with open('p.json', 'r') as f:
        try:
            raw = json.load(f)
            data = json.loads(base64.b64decode(raw['content'])) if isinstance(raw, dict) and 'content' in raw else raw
        except:
            print("Erreur decodage"); exit(1)

    videos = data.get('videos', [])
    res_w, res_h = 720, 1280
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    processed = []

    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"o_{i}.ts"
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))

        # Analyse durée
        dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', in_f]).decode().strip() or 2.0)

        # --- FILTRE HOLLYWOOD ---
        # 1. Recadrage intelligent
        # 2. Correction Couleur (Saturation + Contraste + Vibrance)
        # 3. Flou artistique léger sur les bords (Vignette)
        # 4. Bandes noires (Letterbox)
        vf = (f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},"
              f"eq=brightness=0.04:contrast=1.25:saturation=1.4," # Étalonnage Cinéma
              f"vignette='PI/4'," # Effet de focus central
              f"drawbox=y=0:color=black:width=iw:height=ih/12:t=fill," # Bande haut
              f"drawbox=y=ih-ih/12:color=black:width=iw:height=ih/12:t=fill") # Bande bas
        
        # --- TEXTE DYNAMIQUE (STYLE VIRAL) ---
        text = v.get('text', '').strip().upper()
        if text:
            words = text.split()
            w_dur = dur / len(words)
            for idx, w in enumerate(words):
                start, end = idx * w_dur, (idx + 1) * w_dur
                clean_w = w.replace("'", "").replace(":", "")
                
                # Ombre portée et bordure pour un look pro
                vf += (f",drawtext=fontfile='{font}':text='{clean_w}':fontcolor=yellow:fontsize=80:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2:borderw=4:bordercolor=black@0.9:"
                       f"shadowcolor=black@0.6:shadowx=5:shadowy=5:"
                       f"enable='between(t,{start},{end})'")

        # Ajout d'un flash blanc ultra-rapide au changement de clip (0.1s)
        vf += ",drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.1)'"

        subprocess.run(['ffmpeg', '-y', '-i', in_f, '-vf', vf, '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f], check=True)
        processed.append(out_f)

    # Fusion avec fondu au noir final
    with open('list.txt', 'w') as f:
        for n in processed: f.write(f"file '{n}'\n")
    
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-vf', 'fade=t=out:st=28:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', 'output.mp4'], check=True)

if __name__ == "__main__":
    main()
