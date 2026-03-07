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
        output_name = f"out_{i}.mp4"
        with open(input_name, "wb") as vf:
            vf.write(base64.b64decode(v['data']))

        text = v.get('text', '').replace("'", "\\'").upper()
        
        # --- EFFET PUNCHY FILTERS ---
        # 1. Zoom constant (Ken Burns rapide)
        # 2. Flash blanc au début (0.1s)
        # 3. Correction couleur vibrante
        video_filter = (
            f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},"
            f"zoompan=z='min(zoom+0.0015,1.5)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={res_w}x{res_h},"
            f"eq=saturation=1.2:contrast=1.1," # Couleurs plus vives
            f"fade=t=in:st=0:d=0.1:color=white" # Flash blanc rapide au lieu de transition longue
        )
        
        if text:
            # Texte "TikTok Style" : Jaune ou Blanc, centré, avec bordure noire épaisse
            video_filter += (
                f",drawtext=text='{text}':fontcolor=yellow:fontsize=60:"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:borderw=4:bordercolor=black"
            )

        cmd = [
            'ffmpeg', '-y', '-i', input_name,
            '-vf', video_filter,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', # Qualité haute, encodage rapide
            '-c:a', 'aac', '-af', 'volume=1.5', # Son boosté de 50%
            output_name
        ]
        subprocess.run(cmd, check=True)
        processed_clips.append(output_name)

    # Fusion finale
    with open('list.txt', 'w') as f:
        for n in processed_clips: f.write(f"file '{n}'\n")

    # On utilise concat avec un léger re-encodage pour garantir la fluidité
    final_cmd = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt',
        '-c', 'copy', 'output.mp4'
    ]
    
    subprocess.run(final_cmd, check=True)
    print("Vidéo ULTRA-PUNCHY générée !")

if __name__ == "__main__":
    main()
