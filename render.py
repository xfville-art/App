import json, base64, os, subprocess

# CONFIGURATION ÉPURÉE
CFG = {
    "res": "720x1280",
    "fps": 24,
    "text_size": 42,
    "watermark": "@LesCrados.ai"
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    print(f"Executing: {cmd[:100]}...")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FFmpeg Error: {res.stderr}")
    return res

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    processed = []
    
    # 1. NORMALISATION INDIVIDUELLE (Vidéo + Audio Stéréo forcé)
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"seg_{i}.mp4"
        
        # On prépare chaque clip pour qu'il soit identique en tout point
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']}"
        # On force l'audio en stéréo 44100Hz, même si la source est muette
        cmd = (f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo '
               f'-filter_complex "[0:v]{vf}[v];[0:a][1:a]amix=inputs=2:duration=first[a]" '
               f'-map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac -ar 44100 {out}')
        run(cmd)
        processed.append(out)

    # 2. CONCATÉNATION (Méthode la plus stable du monde)
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base.mp4")

    # 3. GÉNÉRATION DU SCRIPT DE FILTRES (Évite les erreurs de terminal)
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 base.mp4")
    try:
        total_dur = float(res.stdout.strip())
    except:
        total_dur = 15.0

    dur_seg = total_dur / len(processed)
    punchlines = ["COLLECTION 2026", "MUTATION GENIALE", "L ART DU PIRE", "EXPERIENCE INTERDITE"]

    with open("myscript.txt", "w") as f:
        # Watermark
        f.write(f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=22:fontcolor=white@0.3:x=w-text_w-40:y=60,")
        # Textes dynamiques
        texts = []
        for i in range(len(processed)):
            t_start = i * dur_seg
            t_end = (i + 1) * dur_seg
            txt = punchlines[i % len(punchlines)]
            # On utilise des paramètres simples pour éviter tout bug
            texts.append(f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:fontcolor=white:"
                         f"shadowcolor=black@0.8:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h-220:enable='between(t,{t_start},{t_end})'")
        f.write(",".join(texts))

    # 4. RENDU FINAL (Lecture du script de filtres)
    # L'option -filter_script:v est le secret des pros
    run(f"ffmpeg -y -i base.mp4 -filter_script:v myscript.txt -c:v libx264 -crf 18 -c:a copy output.mp4")
    
    print(f"💎 MASTER V41 TERMINE - DUREE : {total_dur:.2f}s")

if __name__ == "__main__":
    start()
