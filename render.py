import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'):
        print("ERREUR : p.json introuvable."); exit(1)

    # 1. Chargement robuste des données
    with open('p.json', 'r') as f:
        content = json.load(f)
        raw_data = base64.b64decode(content['content']) if 'content' in content else json.dumps(content).encode()
        data = json.loads(raw_data)

    videos = data.get('videos', [])
    opt = data.get('options', {})
    res_w, res_h = opt.get('resolution', '720x1280').split('x')
    fps = opt.get('fps', 30)

    # 2. Traitement intelligent de chaque clip
    processed_clips = []
    for i, v in enumerate(videos):
        input_name = f"raw_{i}.mp4"
        output_name = f"proc_{i}.ts" # Utilisation de .ts pour une fusion parfaite
        
        with open(input_name, "wb") as vf:
            vf.write(base64.b64decode(v['data']))

        # --- LOGIQUE D'INTELLIGENCE ---
        # Filtre : Mise à l'échelle + Zoom progressif (si activé)
        # On simule un zoom de 1.0 à 1.1 sur la durée du clip
        zoom_filter = f"scale=8000:-1,zoompan=z='min(zoom+0.001,1.1)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={res_w}x{res_h}"
        
        # Ajout du texte (Caption) avec style "IA" (fond noir semi-transparent)
        text = v.get('text', '').replace("'", "\\'").upper()
        text_filter = ""
        if text:
            text_filter = (f",drawtext=text='{text}':fontcolor=white:fontsize=48:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                           f":x=(w-text_w)/2:y=(h-text_h)-150:box=1:boxcolor=black@0.5:boxborderw=10")

        # Application des filtres et conversion en flux de transport (.ts) pour éviter les bugs de concaténation
        cmd_clip = [
            'ffmpeg', '-y', '-i', input_name,
            '-vf', f"{zoom_filter}{text_filter},format=yuv420p",
            '-c:v', 'libx264', '-preset', 'veryfast', '-r', str(fps), output_name
        ]
        subprocess.run(cmd_clip, check=True)
        processed_clips.append(output_name)

    # 3. Assemblage Final
    with open('list.txt', 'w') as f:
        for n in processed_clips: f.write(f"file '{n}'\n")

    final_cmd = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt',
        '-c', 'copy', 'output.mp4'
    ]
    
    print("Assemblage final...")
    subprocess.run(final_cmd, check=True)
    print("Vidéo générée avec succès !")

if __name__ == "__main__":
    main()
