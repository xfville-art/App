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
    # On utilise la police système par défaut de Ubuntu GitHub
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    processed = []

    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"o_{i}.ts"
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))

        # Analyse durée
        dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', in_f]).decode().strip() or 2.0)

        # --- FILTRE HOLLYWOOD CINÉMA ---
        # 1. Mise au format & Crop
        # 2. Correction colorimétrique (Vibrance + Contraste)
        # 3. Bandes noires cinéma (Letterbox)
        vf = (f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},"
              f"eq=brightness=0.02:contrast=1.1:saturation=1.3," # Effet Cinéma
              f"drawbox=y=0:color=black:width=iw:height=ih/10:t=fill," # Bande haut
              f"drawbox=y=ih-ih/10:color=black:width=iw:height=ih/10:t=fill") # Bande bas
        
        # --- TEXTE ANIMÉ IA ---
        text = v.get('text', '').strip().upper()
        if text:
            words = text.split()
            w_dur = dur / len(words)
            for idx, w in enumerate(words):
                start, end = idx * w_dur, (idx + 1) * w_dur
                clean_w = w.replace("'", "").replace(":", "")
                # Texte centré avec contour épais (Style Blockbuster)
                vf += (f",drawtext=fontfile='{font}':text='{clean_w}':fontcolor=white:fontsize=75:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2:borderw=4:bordercolor=black@0.8:"
                       f"enable='between(t,{start},{end})'")

        # Encodage rapide
        subprocess.run(['ffmpeg', '-y', '-i', in_f, '-vf', vf, '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f], check=True)
        processed.append(out_f)

    # Fusion finale
    with open('list.txt', 'w') as f:
        for n in processed: f.write(f"file '{n}'\n")
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', '-pix_fmt', 'yuv420p', 'output.mp4'], check=True)

if __name__ == "__main__":
    main()
