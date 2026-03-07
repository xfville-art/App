import json, base64, os, subprocess

def main():
    if not os.path.exists('p.json'):
        print("Erreur: p.json introuvable")
        return
        
    with open('p.json', 'r') as f:
        data = json.load(f)
    
    # Extraction propre des données envoyées par l'App
    content = data.get('content', data)
    if isinstance(content, str):
        decoded = json.loads(base64.b64decode(content).decode('utf-8'))
    else:
        decoded = content
        
    videos = decoded.get('videos', [])
    segments = []

    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"s_{i}.ts"
        with open(in_f, "wb") as f:
            f.write(base64.b64decode(v['data']))

        # CONFIGURATION IA PUNCHY
        # 1. Zoompan : crée un zoom avant constant pour dynamiser l'image fixe
        # 2. Drawtext : texte animé (pulse) avec contour épais
        txt = v.get('text', '').upper().replace("'", "\\'")
        
        filter_complex = (
            f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"zoompan=z='zoom+0.002':d=125:s=1080x1920," 
            f"drawtext=text='{txt}':fontcolor=yellow:fontsize='(w/10+20*sin(t*10))':"
            f"x=(w-text_w)/2:y=(h-text_h)/2+300:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"borderw=8:bordercolor=black"
        )

        cmd = [
            'ffmpeg', '-y', '-i', in_f, 
            '-vf', filter_complex, 
            '-c:v', 'libx264', '-preset', 'ultrafast', '-t', '5', 
            '-pix_fmt', 'yuv420p', out_f
        ]
        
        if subprocess.run(cmd).returncode == 0:
            segments.append(out_f)

    if segments:
        with open('concat.txt', 'w') as f:
            for s in segments: f.write(f"file '{s}'\n")
        # Génération du fichier final attendu par l'Action GitHub
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', 'output.mp4'])
        print("Rendu terminé avec succès.")

if __name__ == "__main__":
    main()
