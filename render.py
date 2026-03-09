import json, base64, os, subprocess, re

CFG = {"total_dur": 15.0, "res": "720x1280", "text_size": 55}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_best_cut(file, target_t):
    """ Trouve le silence le plus proche du point de coupe théorique """
    res = run(f"ffmpeg -i {file} -af silencedetect=n=-30dB:d=0.1 -f null - 2>&1")
    silences = re.findall(r"silence_start: ([\d.]+)", res.stdout)
    if not silences: return target_t
    # On cherche le silence le plus proche de notre cible
    closest = min(silences, key=lambda x: abs(float(x) - target_t))
    return float(closest)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    num = len(videos)
    target_seg = CFG["total_dur"] / num
    processed = []
    
    punchlines = ["EXPÉRIENCE", "MUTATION", "CHAOS", "CRADOS 2026"]

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        # LOGIQUE DE COUPE INTELLIGENTE
        # Au lieu de couper brutalement à 3.75s, on cherche un silence entre 3.0s et 4.5s
        actual_dur = get_best_cut(raw, target_seg)
        
        out = f"s{i}.mp4"
        vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setpts=PTS-STARTPTS,cas=0.5"
        
        # On coupe au 'silence' détecté pour ne pas couper la parole
        run(f'ffmpeg -y -i {raw} -t {actual_dur} -vf "{vf}" -c:v libx264 -crf 17 -c:a aac {out}')
        processed.append((out, actual_dur))

    # Concaténation
    with open("l.txt", "w") as f:
        for c, _ in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -safe 0 -i l.txt -c:v copy -c:a copy base.mp4")

    # Placement des textes synchronisé sur les nouvelles durées
    text_filters = []
    current_time = 0
    for i, (out, dur) in enumerate(processed):
        txt = punchlines[i % len(punchlines)]
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=yellow:borderw=10:bordercolor=black:"
                 f"x=(w-text_w)/2:y=h*0.75:enable='between(t,{current_time},{current_time+dur})'")
        text_filters.append(f_txt)
        current_time += dur

    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{','.join(text_filters)}\" "
        f"-c:v libx264 -crf 18 -c:a copy -shortest output.mp4"
    )
    run(final_cmd)
    print("✅ Rendu v30 terminé : Raccords calés sur les silences audio.")

if __name__ == "__main__":
    start()
