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
    fps = opt.get('fps', 30)

    processed_clips = []
    
    for i, v in enumerate(videos):
        input_name = f"in_{i}.mp4"
        output_name = f"out_{i}.ts" # .ts est plus stable pour la fusion
        with open(input_name, "wb") as vf:
            vf.write(base64.b64decode(v['data']))

        text = v.get('text', '').replace("'", "\\'").upper()
        
        # --- FILTRES PUNCHY (Version Stable) ---
        # On remplace zoompan par un scale/crop dynamique plus simple
        # On ajoute un flash blanc de 0.1s au début de chaque clip
        video_filter = (
            f"scale={res_w*2}:-1,crop={res_w}:{res_h},setsar=1," # Recadrage propre
            f"drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.1)'," # Flash blanc
            f"eq=saturation=1.3:contrast=1.1" # Boost couleurs
        )
        
        if text:
            # Style TikTok : Texte Jaune, Bordure Noire, au milieu
            video_filter += (
                f",drawtext=text='{text}':fontcolor=yellow:fontsize=65:"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:borderw=5:bordercolor=black"
            )

        cmd = [
            'ffmpeg', '-y', '-i', input_name,
            '-vf', video_filter,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
            '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-af', 'volume=1.5',
            '-t', '5', # Limite à 5s par clip pour éviter les fichiers géants
            output_name
        ]
        subprocess.run(cmd, check=True)
        processed_clips.append(output_name)

    # Fusion finale
    with open('list.txt', 'w') as f:
        for n in processed_clips: f.write(f"file '{n}'\n")

    # On ré-encode légèrement la fin pour garantir la lecture sur iPhone/Android
    final_cmd = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
        'output.mp4'
    ]
    
    subprocess.run(final_cmd, check=True)
    print("Vidéo terminée avec succès !")

if __name__ == "__main__":
    main()
