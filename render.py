import json, base64, os, subprocess

CFG = {
    "res": "720x1280",
    "fps": 24,
    "text_size": 42,
    "watermark": "@LesCrados.ai"
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    # On affiche l'erreur en cas d'échec pour débugger
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERREUR FFmpeg: {result.stderr}")
    return result

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    processed = []
    
    # 1. NORMALISATION (Video + Audio silencieux forcé)
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"segment_{i}.mp4"
        
        # On crée un clip propre avec une piste audio de secours pour éviter les bugs de concat
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']}"
        cmd = (f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo '
               f'-filter_complex "[0:v]{vf}[v];[0:a][1:a]amix=inputs=2:duration=first[a]" '
               f'-map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac -shortest {out}')
        run(cmd)
        processed.append(out)

    # 2. CONCATÉNATION (Méthode Demuxer, la plus stable)
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base.mp4")

    # 3. HABILLAGE TEXTE (On utilise une chaîne de texte ultra-simple)
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 base.mp4")
    try:
        total_dur = float(res.stdout.strip())
    except:
        total_dur = 15.0

    dur_per_txt = total_dur / len(processed)
    punchlines = ["EXPERIENCE INTERDITE", "MUTATION GENIALE", "L'ART DU PIRE", "COLLECTION 2026"]
    
    # On construit la commande drawtext manuellement sans caractères spéciaux
    filters = []
    # Watermark discret en haut
    filters.append(f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=20:fontcolor=white@0.3:x=w-text_w-40:y=60")
    
    for i in range(len(processed)):
        t_start = i * dur_per_txt
        t_end = (i + 1) * dur_per_txt
        txt = punchlines[i % len(punchlines)]
        # Style moderne : blanc, sans bordure, juste une ombre portée douce
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:fontcolor=white:"
                 f"shadowcolor=black@0.8:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h-220:enable='between(t,{t_start},{t_end})'")
        filters.append(f_txt)

    # On applique tous les textes d'un coup sur la vidéo finale
    filter_string = ",".join(filters)
    run(f'ffmpeg -y -i base.mp4 -vf "{filter_string}" -c:v libx264 -crf 18 -c:a copy output.mp4')
    
    print(f"🎬 RENDU TERMINE - DURÉE : {total_dur:.2f}s")

if __name__ == "__main__":
    start()
