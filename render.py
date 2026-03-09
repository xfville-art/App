import json, base64, os, subprocess, re

# CONFIGURATION STYLE VIRAL (Style 1000026660.mp4)
CFG = {
    "total_dur": 12.0,  # Plus court = plus d'impact
    "res": "720x1280",
    "fps": 24,
    "text_size": 95,
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
    # Durée par clip très courte pour le dynamisme (Jump Cuts)
    dur_seg = CFG["total_dur"] / num
    
    processed = []
    # Textes percutants sans ponctuation pour FFmpeg
    punchlines = ["TROP BIZARRE", "INCROYABLE", "C EST QUOI ?", "ABONNE TOI"]

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        out = f"s{i}.mp4"
        # Montage : Pas de zoom, juste un cadrage parfait 9:16
        # On garde l'audio d'origine (-c:a aac)
        vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        
        cmd = (f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" '
               f'-c:v libx264 -crf 18 -c:a aac -ar 44100 {out}')
        run(cmd)
        processed.append(out)

    # 1. Concaténation Vidéo + Audio
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c:v copy -c:a copy full_base.mp4")

    # 2. Ajout des Textes "Pop" et Watermark
    # On crée une chaîne de filtres pour que chaque texte apparaisse pile sur son clip
    text_filters = []
    for i in range(num):
        t_start = i * dur_seg
        t_end = (i + 1) * dur_seg
        txt = punchlines[i % len(punchlines)]
        color = "white" if i % 2 == 0 else "yellow"
        
        # Style : Gros texte centré, bordure noire très épaisse
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor={color}:borderw=15:bordercolor=black:"
                 f"x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    # Watermark permanent
    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=35:fontcolor=white@0.4:x=w-text_w-50:y=120"
    
    # Rendu Final
    all_filters = ",".join(text_filters)
    final_cmd = (
        f"ffmpeg -y -i full_base.mp4 -vf \"{brand},{all_filters}\" "
        f"-c:v libx264 -c:a copy -pix_fmt yuv420p output.mp4"
    )
    
    print("🎬 Génération du rendu final...")
    run(final_cmd)
    
    if os.path.exists("output.mp4"):
        print("✅ RENDU COMPLET RÉUSSI")

if __name__ == "__main__":
    start()
