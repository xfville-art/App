import json, base64, os, subprocess

CFG = {
    "total_dur": 15.0,
    "res": "720x1280",
    "fps": 24,
    "text_size": 42,       # Taille plus élégante, moins "envahissante"
    "watermark": "@LesCrados.ai"
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    num = len(videos)
    dur_seg = CFG["total_dur"] / num
    processed = []
    
    # Textes "Editorial" - Sobres et percutants
    punchlines = ["EXPÉRIENCE INTERDITE", "MUTATION GÉNIALE", "L'ART DU PIRE", "COLLECTION 2026"]

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # 🎨 ÉTALONNAGE & NETTETÉ PRO
        # unsharp: Améliore les détails de l'IA
        # eq: Légère augmentation de la saturation pour un look "cinéma"
        vf = (f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              f"setpts=PTS-STARTPTS,unsharp=3:3:1.5,eq=saturation=1.15,"
              f"fade=t=in:st=0:d=0.3,fade=t=out:st={dur_seg-0.3}:d=0.3")
        
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 17 -c:a aac -ar 44100 {out}')
        processed.append(out)

    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -safe 0 -i l.txt -c:v copy -c:a copy base.mp4")

    # --- DESIGN TYPOGRAPHIQUE MODERN ---
    text_filters = []
    for i in range(num):
        t_start = i * dur_seg
        t_end = (i + 1) * dur_seg
        txt = punchlines[i % len(punchlines)]
        
        # Style : Texte blanc, ombre portée floue, placement tiers inférieur
        # Animation d'opacité ultra-douce
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:shadowcolor=black@0.7:shadowx=2:shadowy=2:box=1:boxcolor=black@0.2:boxborderw=10:"
                 f"x=(w-text_w)/2:y=h-220:"
                 f"alpha='if(lt(t,{t_start}+0.4), (t-{t_start})/0.4, if(gt(t,{t_end}-0.4), ({t_end}-t)/0.4, 1))':"
                 f"enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    # Watermark signature (très discrète)
    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=24:fontcolor=white@0.15:x=w-text_w-40:y=60"
    
    # Rendu final avec synchronisation forcée
    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},{','.join(text_filters)}\" "
        f"-c:v libx264 -crf 18 -c:a copy -shortest output.mp4"
    )
    
    run(final_cmd)
    print("💎 Rendu v28 MASTER finalisé.")

if __name__ == "__main__":
    start()
