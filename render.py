import json, base64, os, subprocess, re

def split_text_into_timed_parts(text, duration):
    """Découpe le texte en segments pour l'animation"""
    words = text.split()
    if not words: return []
    n = max(1, len(words) // 3) # Groupes de 3 mots
    chunks = [" ".join(words[i:i+n]) for i in range(0, len(words), n)]
    chunk_dur = duration / len(chunks)
    return [(chunk, i*chunk_dur, (i+1)*chunk_dur) for i, chunk in enumerate(chunks)]

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
    fps = opt.get('fps', 30)

    processed_clips = []
    
    for i, v in enumerate(videos):
        input_name = f"in_{i}.mp4"
        output_name = f"out_{i}.ts"
        with open(input_name, "wb") as vf:
            vf.write(base64.b64decode(v['data']))

        # Analyse de la durée réelle du clip via FFmpeg
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_name], capture_output=True, text=True)
        duration = float(probe.stdout.strip() or 2.0)

        # --- FILTRES IA & ANIMATION ---
        # 1. Zoom Panoramique (plus stable)
        video_filter = f"scale=1280:-1,crop={res_w}:{res_h},setsar=1"
        
        # 2. Animation des Textes (Captions Dynamiques)
        text_str = v.get('text', '').replace("'", "\\'").upper()
        if text_str:
            parts = split_text_into_timed_parts(text_str, duration)
            for chunk, start, end in parts:
                # Effet de texte qui "pop" (jaune avec bordure noire)
                video_filter += (
                    f",drawtext=text='{chunk}':fontcolor=yellow:fontsize=70:"
                    f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                    f"x=(w-text_w)/2:y=(h-text_h)/2+100:borderw=5:bordercolor=black:"
                    f"enable='between(t,{start},{end})'"
                )

        # 3. Flash de transition
        video_filter += f",drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.1)'"

        cmd = [
            'ffmpeg', '-y', '-i', input_name,
            '-vf', video_filter,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
            '-c:a', 'aac', '-ar', '44100', '-af', 'volume=1.8',
            output_name
        ]
        subprocess.run(cmd, check=True)
        processed_clips.append(output_name)

    # Fusion finale
    with open('list.txt', 'w') as f:
        for n in processed_clips: f.write(f"file '{n}'\n")

    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', 'output.mp4'], check=True)
    print("Vidéo IA Capcut-Style terminée !")

if __name__ == "__main__":
    main()
