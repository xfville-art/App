import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'):
        print("ERREUR : p.json introuvable."); exit(1)

    with open('p.json', 'r') as f:
        content = json.load(f)
        raw_data = base64.b64decode(content['content']) if 'content' in content else json.dumps(content).encode()
        data = json.loads(raw_data)

    videos = data.get('videos', [])
    opt = data.get('options', {})
    res_w, res_h = 720, 1280
    
    processed_clips = []
    
    # Chemin de la police standard sur Ubuntu GitHub Runner
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    for i, v in enumerate(videos):
        input_name = f"in_{i}.mp4"
        output_name = f"out_{i}.ts"
        with open(input_name, "wb") as vf:
            vf.write(base64.b64decode(v['data']))

        # Récupérer la durée exacte
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_name], capture_output=True, text=True)
        try:
            dur = float(probe.stdout.strip())
        except:
            dur = 2.0

        text_str = v.get('text', '').strip().upper()
        print(f"Traitement clip {i} - Texte: {text_str}")

        # --- FILTRE VIDÉO ---
        # On prépare la base : Scale + Crop + Flash blanc
        video_filter = f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.07)'"
        
        # AJOUT DES MOTS ANIMÉS
        if text_str:
            words = text_str.split()
            word_dur = dur / len(words)
            for idx, word in enumerate(words):
                start = idx * word_dur
                end = (idx + 1) * word_dur
                
                # Nettoyage du texte pour éviter les erreurs FFmpeg
                clean_word = word.replace(":", "\\:").replace("'", "").replace(",", "")
                
                # Ajout du drawtext pour chaque mot
                video_filter += (
                    f",drawtext=fontfile='{font_path}':text='{clean_word}':"
                    f"fontcolor=white:fontsize=90:x=(w-text_w)/2:y=(h-text_h)/2:"
                    f"shadowcolor=black@0.5:shadowx=4:shadowy=4:enable='between(t,{start},{end})'"
                )

        cmd = [
            'ffmpeg', '-y', '-i', input_name,
            '-vf', video_filter,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
            '-c:a', 'aac', '-ac', '2', '-af', 'volume=1.5',
            output_name
        ]
        subprocess.run(cmd, check=True)
        processed_clips.append(output_name)

    # Fusion finale
    with open('list.txt', 'w') as f:
        for n in processed_clips: f.write(f"file '{n}'\n")

    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', 'output.mp4'], check=True)
    print("TERMINÉ avec succès.")

if __name__ == "__main__":
    main()
