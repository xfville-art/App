import json, base64, os, subprocess

CFG = {
    "res": "720x1280",
    "fps": 24,
    "text_size": 45,
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
    
    # 1. NORMALISATION RADICALE
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # Le secret : On génère un silence et on le mélange à l'audio d'origine.
        # Ça force tous les clips à avoir du son, en stéréo, même s'ils étaient muets.
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']},setpts=PTS-STARTPTS"
        
        cmd = (f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo -filter_complex '
               f'"[0:v]{vf}[v];[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a1];'
               f'[a1][1:a]amix=inputs=2:duration=first[aout]" '
               f'-map "[v]" -map "[aout]" -c:v libx264 -crf 18 -c:a aac -shortest {out}')
        run(cmd)
        processed.append(out)

    # 2. CONCATÉNATION PAR LISTE
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    
    run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base_long.mp4")

    # 3. DURÉE ET HABILLAGE
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 base_long.mp4")
    try:
        total_dur = float(res.stdout.strip())
    except:
        total_dur = 10.0

    punchlines = ["EXPÉRIENCE INTERDITE", "MUTATION GÉNIALE", "L'ART DU PIRE", "COLLECTION 2026"]
    dur_per_txt = total_dur / len(processed)
    text_filters = []
    
    for i in range(len(processed)):
        t_start = i * dur_per_txt
        t_end = (i + 1) * dur_per_txt
        txt = punchlines[i % len(punchlines)]
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:shadowcolor=black@0.8:shadowx=3:shadowy=3:"
                 f"x=(w-text_w)/2:y=h-220:enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=24:fontcolor=white@0.2:x=w-text_w-40:y=60"
    
    # 4. RENDU FINAL
    final_filters = f"{brand},{','.join(text_filters)},unsharp=3:3:1.5"
    run(f'ffmpeg -y -i base_long.mp4 -vf "{final_filters}" -c:v libx264 -crf 18 -c:a copy output.mp4')
    
    print(f"🎬 RENDU OK - DURÉE : {total_dur:.2f}s")

if __name__ == "__main__":
    start()
