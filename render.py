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
    
    # 1. NORMALISATION (Video seule pour éviter les conflits audio)
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # On force un format vidéo ultra-standard sans audio pour l'instant
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']},setpts=PTS-STARTPTS"
        run(f'ffmpeg -y -i {raw} -vf "{vf}" -c:v libx264 -crf 18 -an {out}')
        processed.append(out)

    # 2. CONCATÉNATION VIDÉO SANS ÉCHEC
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base_video.mp4")

    # 3. RÉCUPÉRATION DE L'AUDIO (On prend le son global du premier clip ou on mixe)
    # Pour faire simple et robuste, on prend l'audio du fichier r0.mp4
    run("ffmpeg -y -i base_video.mp4 -i r0.mp4 -map 0:v -map 1:a? -c:v copy -c:a aac -shortest base_with_audio.mp4")

    # 4. HABILLAGE (On utilise un fichier de script pour les filtres pour éviter les erreurs de ligne de commande)
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 base_with_audio.mp4")
    try:
        total_dur = float(res.stdout.strip())
    except:
        total_dur = 10.0

    punchlines = ["EXPERIENCE INTERDITE", "MUTATION GENIALE", "L'ART DU PIRE", "COLLECTION 2026"]
    dur_per_txt = total_dur / len(processed)
    
    text_filters = []
    for i in range(len(processed)):
        t_start = i * dur_per_txt
        t_end = (i + 1) * dur_per_txt
        txt = punchlines[i % len(punchlines)]
        # Style épuré : texte blanc, petite ombre, pas de caractères spéciaux
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:shadowcolor=black@0.8:shadowx=2:shadowy=2:"
                 f"x=(w-text_w)/2:y=h-200:enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=20:fontcolor=white@0.3:x=w-text_w-30:y=40"
    
    # 5. RENDU FINAL (On limite le nombre de filtres actifs simultanément)
    all_filters = f"{brand},{','.join(text_filters)}"
    final_cmd = f'ffmpeg -y -i base_with_audio.mp4 -vf "{all_filters}" -c:v libx264 -crf 20 -c:a copy output.mp4'
    run(final_cmd)
    
    print(f"🎬 MASTER V38 OK - DURÉE : {total_dur:.2f}s")

if __name__ == "__main__":
    start()
