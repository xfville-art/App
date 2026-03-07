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
    
    for i, v in enumerate(videos):
        input_name = f"in_{i}.mp4"
        output_name = f"out_{i}.ts"
        with open(input_name, "wb") as vf:
            vf.write(base64.b64decode(v['data']))

        # Analyse précise de la durée du clip
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_name], capture_output=True, text=True)
        try:
            dur = float(probe.stdout.strip())
        except:
            dur = 2.0 # Sécurité

        text_str = v.get('text', '').strip().upper()
        
        # --- FILTRES VIDÉO STYLE IA ---
        # On force le format vertical 9:16 et on améliore le piqué de l'image
        video_filter = f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},unsharp=3:3:1.5"
        
        # LOGIQUE D'ANIMATION MOT PAR MOT
        if text_str:
            words = text_str.split()
            if len(words) > 0:
                word_dur = dur / len(words)
                for idx, word in enumerate(words):
                    start = idx * word_dur
                    end = (idx + 1) * word_dur
                    
                    # Style Anthropic : Blanc pur, sans boîte, ombre portée douce (Glow effect)
                    # Le texte "pop" au centre avec une taille de 80
                    video_filter += (
                        f",drawtext=text='{word}':fontcolor=white:fontsize=85:"
                        f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                        f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.4:shadowx=4:shadowy=4:"
                        f"enable='between(t,{start},{end})'"
                    )

        # Transition Punchy : Flash blanc très court (60ms)
        video_filter += f",drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.06)'"

        cmd = [
            'ffmpeg', '-y', '-i', input_name,
            '-vf', video_filter,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
            '-c:a', 'aac', '-ac', '2', '-af', 'volume=1.8',
            output_name
        ]
        subprocess.run(cmd, check=True)
        processed_clips.append(output_name)

    # Fusion finale propre
    with open('list.txt', 'w') as f:
        for n in processed_clips: f.write(f"file '{n}'\n")

    # Encodage final compatible iPhone/Android (yuv420p)
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', 'output.mp4'], check=True)
    print("Vidéo terminée avec Captions IA Dynamiques.")

if __name__ == "__main__":
    main()
