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
    
    # 1. Normalisation de chaque clip
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # On force la présence d'audio (même silencieux) pour éviter les crashs de concaténation
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']},setpts=PTS-STARTPTS"
        # On utilise 'amix' et 'anullsrc' pour garantir une piste audio valide
        cmd = (f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo -filter_complex '
               f'"[0:v]{vf}[vout];[0:a][1:a]amix=inputs=2:duration=first[aout]" '
               f'-map "[vout]" -map "[aout]" -c:v libx264 -crf 18 -c:a aac -shortest {out}')
        run(cmd)
        processed.append(out)

    # 2. Concaténation par liste (la méthode la plus stable pour éviter les erreurs de syntaxe)
    with open("list.txt", "w") as f:
        for p in processed:
            f.write(f"file '{p}'\n")
            
    # On crée la base longue
    run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy long_base.mp4")

    # 3. Récupération de la durée réelle
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 long_base.mp4")
    try:
        total_dur = float(res.stdout.strip())
    except:
        total_dur = 15.0 # Valeur de secours

    # 4. Habillage Final
    dur_per_txt = total_dur / len(processed)
    punchlines = ["EXPÉRIENCE INTERDITE", "MUTATION GÉNIALE", "L'ART DU PIRE", "COLLECTION 2026"]
    text_filters = []
    
    for i in range(len(processed)):
        t_start = i * dur_per_txt
        t_end = (i + 1) * dur_per_txt
        txt = punchlines[i % len(punchlines)]
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:shadowcolor=black@0.7:shadowx=3:shadowy=3:"
                 f"x=(w-text_w)/2:y=h-220:enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=24:fontcolor=white@0.2:x=w-text_w-40:y=60"
    
    # Rendu FINAL avec filtres de netteté
    final_filters = f"{brand},{','.join(text_filters)},unsharp=3:3:1.5"
    run(f'ffmpeg -y -i long_base.mp4 -vf "{final_filters}" -c:v libx264 -crf 18 -c:a copy output.mp4')
    
    print(f"🎬 RENDU TERMINÉ. DURÉE : {total_dur:.2f}s")

if __name__ == "__main__":
    start()
