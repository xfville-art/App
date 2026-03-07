import json, base64, os, subprocess

def main():
    print("--- DÉBUT DU RENDU VIRACUT ---")
    if not os.path.exists('p.json'):
        print("ERREUR CRITIQUE : p.json introuvable !"); exit(1)

    with open('p.json', 'r') as f:
        try:
            raw = json.load(f)
            # Gestion du format 'content' de l'API GitHub
            if isinstance(raw, dict) and 'content' in raw:
                print("Décodage du format API GitHub...")
                data = json.loads(base64.b64decode(raw['content']))
            else:
                print("Lecture du format JSON direct...")
                data = raw
        except Exception as e:
            print(f"ERREUR JSON : {e}"); exit(1)

    videos = data.get('videos', [])
    print(f"Nombre de clips à traiter : {len(videos)}")

    res_w, res_h = 720, 1280
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    processed = []

    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"o_{i}.ts"
        text = v.get('text', '').strip().upper()
        print(f"Clip {i} : Texte reçu = '{text}'")

        with open(in_f, "wb") as f:
            f.write(base64.b64decode(v['data']))

        # Durée réelle du clip
        dur = 2.0
        try:
            dur_out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', in_f])
            dur = float(dur_out.decode().strip())
        except: pass

        # Filtre Vidéo avec protection des caractères
        vf = f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},setsar=1"
        
        if text:
            words = text.split()
            w_dur = dur / len(words)
            for idx, w in enumerate(words):
                start, end = idx * w_dur, (idx + 1) * w_dur
                # Nettoyage strict pour FFmpeg
                clean_w = w.replace("'", "").replace(":", "").replace(",", "").replace('"', '')
                
                vf += (f",drawtext=fontfile='{font}':text='{clean_w}':fontcolor=white:fontsize=80:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.7:shadowx=5:shadowy=5:"
                       f"borderw=2:bordercolor=black:enable='between(t,{start},{end})'")
        
        vf += ",drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.06)'"

        print(f"Lancement FFmpeg pour le clip {i}...")
        subprocess.run(['ffmpeg', '-y', '-i', in_f, '-vf', vf, '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_f], check=True)
        processed.append(out_f)

    # Fusion
    print("Fusion finale des clips...")
    with open('list.txt', 'w') as f:
        for n in processed: f.write(f"file '{n}'\n")
    
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', '-pix_fmt', 'yuv420p', 'output.mp4'], check=True)
    print("--- RENDU TERMINÉ AVEC SUCCÈS ---")

if __name__ == "__main__":
    main()
