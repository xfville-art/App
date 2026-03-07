import json, base64, os, subprocess

def update_progress(text):
    with open("progress.txt", "w") as f:
        f.write(text)

def main():
    if not os.path.exists('p.json'): 
        print("Erreur: p.json introuvable"); return
        
    with open('p.json', 'r') as f:
        raw = json.load(f)
        # Correction du KeyError : On vérifie si 'content' existe
        content_str = raw.get('content', '')
        if not content_str:
            print("Erreur: Clé 'content' vide"); return
        data = json.loads(base64.b64decode(content_str))

    videos = data.get('videos', [])
    processed = []
    
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"o_{i}.ts"
        # On décode la vidéo envoyée par l'App-2.html
        with open(in_f, "wb") as f: 
            f.write(base64.b64decode(v['data']))
        
        update_progress(f"Rendu Clip {i+1}/{len(videos)}")
        
        # Encodage rapide (optimisé selon tes logs)
        cmd = [
            'ffmpeg', '-y', '-i', in_f,
            '-vf', f"scale=720:1280,drawtext=text='{v.get('text','')}':fontcolor=yellow:fontsize=60:x=(w-text_w)/2:y=(h-text_h)/2",
            '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f
        ]
        subprocess.run(cmd)
        processed.append(out_f)

    # Fusion finale
    if processed:
        with open('list.txt', 'w') as f:
            for n in processed: f.write(f"file '{n}'\n")
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")

if __name__ == "__main__":
    main()
