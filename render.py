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
    res_w, res_h = 720, 1280 # Format Portrait Standard
    fps = opt.get('fps', 30)

    processed_clips = []
    
    # 1. Préparation de chaque clip avec effets
    for i, v in enumerate(videos):
        input_name = f"in_{i}.mp4"
        output_name = f"out_{i}.mp4"
        with open(input_name, "wb") as vf:
            vf.write(base64.b64decode(v['data']))

        # Extraction du texte et nettoyage
        text = v.get('text', '').replace("'", "\\'").upper()
        
        # Filtre FFmpeg Complexe : 
        # - Mise à l'échelle (Cover) 
        # - Texte avec ombre portée 
        # - Fondu entrant/sortant (Fade)
        video_filter = (
            f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},"
            f"fade=t=in:st=0:d=0.5,fade=t=out:st=1.5:d=0.5" # Fondu de 0.5s
        )
        
        if text:
            video_filter += (
                f",drawtext=text='{text}':fontcolor=white:fontsize=50:"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.6:shadowx=4:shadowy=4"
            )

        cmd = [
            'ffmpeg', '-y', '-i', input_name,
            '-vf', video_filter,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '22',
            '-c:a', 'aac', '-b:a', '128k', # On garde le SON
            output_name
        ]
        subprocess.run(cmd, check=True)
        processed_clips.append(output_name)

    # 2. Fusion finale de tous les clips
    with open('list.txt', 'w') as f:
        for n in processed_clips: f.write(f"file '{n}'\n")

    final_cmd = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt',
        '-c', 'copy', 'output.mp4'
    ]
    
    subprocess.run(final_cmd, check=True)
    print("Vidéo Pro générée !")

if __name__ == "__main__":
    main()
