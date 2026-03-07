import json, base64, os, subprocess, sys

def update_progress(text):
    print(f"PROGRESS: {text}")
    with open("progress.txt", "w") as f:
        f.write(text)

def main():
    if not os.path.exists('p.json'):
        update_progress("ERREUR: p.json introuvable")
        return

    try:
        with open('p.json', 'r') as f:
            raw = json.load(f)
        
        # Décodage sécurisé du contenu GitHub
        content = raw.get('content', raw)
        if isinstance(content, str):
            decoded_bytes = base64.b64decode(content)
            data = json.loads(decoded_bytes.decode('utf-8'))
        else:
            data = content
            
        videos = data.get('videos', [])
        if not videos:
            update_progress("ERREUR: Aucun clip trouvé")
            return
    except Exception as e:
        update_progress(f"ERREUR JSON: {str(e)}")
        return

    segments = []
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        update_progress(f"Traitement Clip {i+1}/{len(videos)}...")

        try:
            with open(in_f, "wb") as f:
                f.write(base64.b64decode(v['data']))

            # Animation IA : Zoom + Texte dynamique
            txt = v.get('text','').upper().replace("'", "\\'")
            filter_str = (
                f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
                f"zoompan=z='zoom+0.002':d=125:s=720x1280,"
                f"drawtext=text='{txt}':fontcolor=yellow:fontsize='80+20*sin(2*3.14*t/0.5)':"
                f"x=(w-text_w)/2:y=(h-text_h)/2:borderw=5:bordercolor=black"
            )

            cmd = ['ffmpeg', '-y', '-i', in_f, '-vf', filter_str, '-c:v', 'libx264', '-preset', 'ultrafast', '-t', '5', out_f]
            if subprocess.run(cmd).returncode == 0:
                segments.append(out_f)
        except Exception as e:
            print(f"Erreur sur clip {i}: {e}")

    # Finalisation
    if segments:
        update_progress("Fusion finale...")
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'copy', 'output.mp4'])
        update_progress("COMPLETED")
    else:
        update_progress("ECHEC: Aucun fichier produit")

if __name__ == "__main__":
    main()
