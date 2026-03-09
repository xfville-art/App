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
    
    # 1. Préparation des segments individuels (Normalisation)
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # On force le ré-encodage complet pour que tous les clips aient les mêmes propriétés
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']},setpts=PTS-STARTPTS"
        run(f'ffmpeg -y -i {raw} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac -af "asetpts=PTS-STARTPTS" -ar 44100 {out}')
        processed.append(out)

    # 2. Concaténation complexe (Vidéo + Audio cumulés)
    # Cette méthode additionne physiquement les durées au lieu de les superposer
    filter_complex = ""
    for i in range(len(processed)):
        filter_complex += f"[{i}:v][i:a]" # Utilise la vidéo et l'audio de chaque fichier
    
    inputs = " ".join([f"-i {p}" for p in processed])
    concat_cmd = (f"ffmpeg -y {inputs} -filter_complex \""
                  f"{''.join([f'[{i}:v][{i}:a]' for i in range(len(processed))])}concat=n={len(processed)}:v=1:a=1[v][a]\" "
                  f"-map \"[v]\" -map \"[a]\" -c:v libx264 -crf 18 -c:a aac long_base.mp4")
    run(concat_cmd)

    # 3. Récupération de la nouvelle durée réelle
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 long_base.mp4")
    total_dur = float(res.stdout.strip())
    dur_per_txt = total_dur / len(processed)

    # 4. Habillage (Textes + Watermark)
    punchlines = ["EXPÉRIENCE INTERDITE", "MUTATION GÉNIALE", "L'ART DU PIRE", "COLLECTION 2026"]
    text_filters = []
    for i in range(len(processed)):
        t_start = i * dur_per_txt
        t_end = (i + 1) * dur_per_txt
        txt = punchlines[i % len(punchlines)]
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:shadowcolor=black@0.6:shadowx=3:shadowy=3:"
                 f"x=(w-text_w)/2:y=h-220:enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=24:fontcolor=white@0.2:x=w-text_w-40:y=60"
    
    # Rendu Final sans aucune restriction de durée
    final_filters = f"{brand},{','.join(text_filters)}"
    run(f'ffmpeg -y -i long_base.mp4 -vf "{final_filters}" -c:v libx264 -crf 18 -c:a copy output.mp4')
    
    print(f"🎬 Rendu v35 terminé. DURÉE RÉELLE : {total_dur:.2f}s")

if __name__ == "__main__":
    start()
