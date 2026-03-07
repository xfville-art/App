import json, base64, os, subprocess

# Installation automatique de Whisper au premier lancement
try:
    import whisper
except ImportError:
    subprocess.run(['pip', 'install', 'openai-whisper', 'setuptools-rust'], check=True)
    import whisper

def main():
    if not os.path.exists('p.json'):
        print("Erreur : p.json absent"); exit(1)

    # Chargement du modèle IA (Base est rapide et précis)
    print("Chargement de l'IA Whisper...")
    model = whisper.load_model("base")

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

        # --- ÉTAPE IA : GÉNÉRATION DU TEXTE AUTOMATIQUE ---
        print(f"L'IA analyse le clip {i}...")
        result = model.transcribe(in_f)
        auto_text = result['text'].strip().upper()
        print(f"Texte généré par IA : {auto_text}")

        # Analyse durée pour le timing
        dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', in_f]).decode().strip() or 2.0)

        # --- FILTRE HOLLYWOOD ---
        vf = (f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},"
              f"eq=brightness=0.03:contrast=1.2:saturation=1.4," # Look Cinéma
              f"drawbox=y=0:color=black:width=iw:height=ih/10:t=fill," # Bande Noire
              f"drawbox=y=ih-ih/10:color=black:width=iw:height=ih/10:t=fill")

        # --- ANIMATION DES MOTS GÉNÉRÉS ---
        if auto_text:
            words = auto_text.split()
            w_dur = dur / len(words) if len(words) > 0 else dur
            for idx, w in enumerate(words):
                start, end = idx * w_dur, (idx + 1) * w_dur
                clean_w = w.replace("'", "").replace(":", "").replace('"', '')
                vf += (f",drawtext=fontfile='{font}':text='{clean_w}':fontcolor=white:fontsize=70:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2:borderw=3:bordercolor=black@0.8:"
                       f"enable='between(t,{start},{end})'")

        subprocess.run(['ffmpeg', '-y', '-i', in_f, '-vf', vf, '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f], check=True)
        processed.append(out_f)

    # Fusion finale
    with open('list.txt', 'w') as f:
        for n in processed: f.write(f"file '{n}'\n")
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', 'output.mp4'], check=True)

if __name__ == "__main__":
    main()
