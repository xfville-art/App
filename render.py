import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'):
        print("Erreur : p.json manquant"); exit(1)

    with open('p.json', 'r') as f:
        try:
            raw = json.load(f)
            data = json.loads(base64.b64decode(raw['content'])) if isinstance(raw, dict) and 'content' in raw else raw
        except:
            print("Erreur JSON"); exit(1)

    videos = data.get('videos', [])
    res_w, res_h = 720, 1280
    # Chemin absolu garanti sur GitHub Runner
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    processed = []

    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"o_{i}.ts"
        with open(in_f, "wb") as f:
            f.write(base64.b64decode(v['data']))

        # Analyse durée
        dur_out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', in_f])
        dur = float(dur_out.decode().strip() or 2.0)

        # Filtre de base : Mise au format 9:16
        vf = f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},setsar=1"
        
        # --- LOGIQUE D'ANIMATION IA MOT PAR MOT ---
        text = v.get('text', '').strip().upper()
        if text:
            words = text.split()
            w_dur = dur / len(words)
            for idx, w in enumerate(words):
                start = idx * w_dur
                end = (idx + 1) * w_dur
                # Nettoyage des caractères spéciaux pour FFmpeg
                clean_w = w.replace("'", "").replace(":", "").replace(",", "")
                # Ajout du filtre drawtext avec ENABLE pour le timing
                vf += (f",drawtext=fontfile='{font}':text='{clean_w}':fontcolor=white:fontsize=80:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.6:shadowx=4:shadowy=4:"
                       f"enable='between(t,{start},{end})'")

        # Transition Punchy (Flash blanc 0.05s)
        vf += ",drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.05)'"

        # Encodage du segment
        subprocess.run(['ffmpeg', '-y', '-i', in_f, '-vf', vf, '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-ar', '44100', out_f], check=True)
        processed.append(out_f)

    # Fusion
    with open('list.txt', 'w') as f:
        for n in processed: f.write(f"file '{n}'\n")
    
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', '-pix_fmt', 'yuv420p', 'output.mp4'], check=True)

if __name__ == "__main__":
    main()
