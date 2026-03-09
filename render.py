import json, base64, os, subprocess

CFG = {
    "res": "720x1280",
    "fps": 24,
    "text_size": 40,
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
    
    # 1. Normalisation Vidéo (Sans son pour l'instant)
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']},setpts=PTS-STARTPTS"
        run(f'ffmpeg -y -i {raw} -vf "{vf}" -c:v libx264 -crf 18 -an {out}')
        processed.append(out)

    # 2. Assemblage des clips
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base_video.mp4")

    # 3. Récupération de l'audio et durée
    run("ffmpeg -y -i base_video.mp4 -i r0.mp4 -map 0:v -map 1:a? -c:v copy -c:a aac -shortest base_audio.mp4")
    
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 base_audio.mp4")
    try:
        total_dur = float(res.stdout.strip())
    except:
        total_dur = 12.0

    # 4. CRÉATION DU FICHIER DE FILTRES (C'est ici que ça change tout !)
    dur_per_txt = total_dur / len(processed)
    punchlines = ["EXPÉRIENCE INTERDITE", "MUTATION GÉNIALE", "L'ART DU PIRE", "COLLECTION 2026"]
    
    filter_lines = []
    # Watermark
    filter_lines.append(f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=24:fontcolor=white@0.2:x=w-text_w-40:y=60")
    
    # Textes
    for i in range(len(processed)):
        t_start = i * dur_per_txt
        t_end = (i + 1) * dur_per_txt
        txt = punchlines[i % len(punchlines)]
        filter_lines.append(
            f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:fontcolor=white:"
            f"shadowcolor=black@0.8:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h-200:enable='between(t,{t_start},{t_end})'"
        )

    with open("filters.txt", "w") as f:
        f.write(",".join(filter_lines))

    # 5. RENDU FINAL (Lecture du fichier de filtres)
    # L'option -filter_script évite les problèmes de guillemets dans la ligne de commande
    run(f'ffmpeg -y -i base_audio.mp4 -filter_script:v filters.txt -c:v libx264 -crf 18 -c:a copy output.mp4')
    
    print(f"✅ RENDU v39 MASTER TERMINÉ - {total_dur:.2f}s")

if __name__ == "__main__":
    start()
