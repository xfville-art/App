import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'):
        print("ERREUR : p.json introuvable."); exit(1)

    with open('p.json', 'r') as f:
        try:
            full_data = json.load(f)
            # Si le JSON vient de l'API GitHub, les données sont dans 'content'
            if isinstance(full_data, dict) and 'content' in full_data:
                raw_json = base64.b64decode(full_data['content'])
                data = json.loads(raw_json)
            else:
                # Sinon, on lit le JSON directement
                data = full_data
        except Exception as e:
            print(f"Erreur de lecture JSON : {e}"); exit(1)

    videos = data.get('videos', [])
    # Configuration des textes animés (Style Anthropic)
    res_w, res_h = 720, 1280
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    
    processed_clips = []
    for i, v in enumerate(videos):
        fname = f"c_{i}.mp4"
        out_name = f"c_{i}.ts"
        with open(fname, "wb") as vf:
            vf.write(base64.b64decode(v['data']))

        # Calcul de la durée pour l'animation
        dur_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', fname]
        dur = float(subprocess.check_output(dur_cmd).decode().strip() or 2.0)

        # Filtre Vidéo + Texte Animé Mot par Mot
        v_filter = f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,crop={res_w}:{res_h},drawbox=y=0:color=white:width=iw:height=ih:t=fill:enable='between(t,0,0.07)'"
        
        text = v.get('text', '').upper()
        if text:
            words = text.split()
            w_dur = dur / len(words)
            for idx, w in enumerate(words):
                v_filter += f",drawtext=fontfile='{font_path}':text='{w}':fontcolor=white:fontsize=90:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.5:shadowx=4:shadowy=4:enable='between(t,{idx*w_dur},{(idx+1)*w_dur})'"

        subprocess.run(['ffmpeg', '-y', '-i', fname, '-vf', v_filter, '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', out_name], check=True)
        processed_clips.append(out_name)

    # Concaténation finale
    with open('list.txt', 'w') as f:
        for n in processed_clips: f.write(f"file '{n}'\n")
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', '-pix_fmt', 'yuv420p', 'output.mp4'], check=True)

if __name__ == "__main__":
    main()
