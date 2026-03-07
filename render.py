import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'):
        print("ERREUR : p.json introuvable."); exit(1)

    # Lecture du fichier p.json
    with open('p.json', 'r') as f:
        content = json.load(f)
        # Si GitHub Actions lit le fichier, il est soit brut, soit dans ['content']
        if isinstance(content, dict) and 'content' in content:
            raw_data = base64.b64decode(content['content'])
        else:
            raw_data = json.dumps(content).encode()
        
        data = json.loads(raw_data)

    videos = data.get('videos', [])
    opt = data.get('options', {})
    
    # 1. Extraire les clips
    input_files = []
    for i, v in enumerate(videos):
        fname = f"c{i}.mp4"
        with open(fname, "wb") as vf:
            vf.write(base64.b64decode(v['data']))
        input_files.append(fname)

    # 2. Créer la liste pour FFmpeg
    with open('list.txt', 'w') as f:
        for n in input_files: f.write(f"file '{n}'\n")

    # 3. Préparer les filtres (Résolution + Textes)
    res = opt.get('resolution', '720x1280').replace('x', ':')
    
    # Construction du filtre de texte si présent
    video_filter = f"scale={res},fps={opt.get('fps', 30)}"
    
    # Ajout du texte au milieu de la vidéo (Captions)
    for v in videos:
        text = v.get('text', '').replace("'", "")
        if text:
            video_filter += f",drawtext=text='{text}':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,2)'"

    # 4. Lancer FFmpeg
    cmd = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt',
        '-vf', video_filter,
        '-c:v', 'libx264', '-crf', str(opt.get('crf', 23)),
        '-pix_fmt', 'yuv420p', 'output.mp4'
    ]

    print("Rendu en cours...")
    subprocess.run(cmd, check=True)
    print("Terminé : output.mp4")

if __name__ == "__main__":
    main()
