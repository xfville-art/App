import json, base64, os, subprocess

CFG = {
    "res": "720x1280",
    "fps": 24,
    "text_size": 50,
    "watermark": "@LesCrados.ai"
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    processed = []
    
    # Étape 1 : Préparation de chaque clip (sans aucune coupe de temps)
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # On traite le visuel mais on garde l'audio original de chaque clip
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']},setpts=PTS-STARTPTS"
        run(f'ffmpeg -y -i {raw} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac -af "asetpts=PTS-STARTPTS" {out}')
        processed.append(out)

    # Étape 2 : Concaténation totale (Vidéo + Audio de tous les clips)
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    
    # Utilisation du protocole concat pour fusionner les flux sans perte de durée
    run("ffmpeg -y -f concat -safe 0 -i l.txt -c copy full_temp.mp4")

    # Étape 3 : Analyse de la durée réelle pour placer les textes
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 full_temp.mp4")
    total_dur = float(res.stdout.strip())
    dur_per_segment = total_dur / len(processed)

    # Étape 4 : Ajout des filtres visuels et textes sur la durée complète
    punchlines = ["EXPÉRIENCE INTERDITE", "MUTATION GÉNIALE", "L'ART DU PIRE", "COLLECTION 2026"]
    text_filters = []
    for i in range(len(processed)):
        t_start = i * dur_per_segment
        t_end = (i + 1) * dur_per_segment
        txt = punchlines[i % len(punchlines)]
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:shadowcolor=black@0.6:shadowx=3:shadowy=3:"
                 f"x=(w-text_w)/2:y=h-220:enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=24:fontcolor=white@0.2:x=w-text_w-40:y=60"
    
    # Rendu final sans l'option -shortest qui pourrait couper la vidéo prématurément
    final_filters = f"{brand},{','.join(text_filters)},unsharp=3:3:1.5"
    run(f'ffmpeg -y -i full_temp.mp4 -vf "{final_filters}" -c:v libx264 -crf 18 -c:a copy output.mp4')
    
    print(f"🎬 Rendu FINAL terminé. Durée : {total_dur:.2f} secondes.")

if __name__ == "__main__":
    start()
