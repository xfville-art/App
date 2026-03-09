import json, base64, os, subprocess, re

# Configuration optimisée pour la fluidité
CFG = {"total_dur": 26.0, "res": "720x1280", "fps": 24}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips_data = data.get('videos', [])
    num = len(clips_data)
    dur_seg = CFG["total_dur"] / num
    
    processed = []
    texts = ["C'EST IMMONDE", "REGARDE BIEN", "T'ES PRÊT ?", "ABONNE-TOI"] # Fallback punchy

    for i, v in enumerate(clips_data):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        # 1. Rendu du segment : Mise à l'échelle propre + Léger Ken Burns (Zoom lent)
        out = f"s{i}.mp4"
        # On simule un mouvement de caméra lent (1.0 à 1.1) très pro
        vf = (f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              f"zoompan=z='min(zoom+0.001,1.1)':d={int(dur_seg*CFG['fps'])}:s=720x1280")
        
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 -an {out}')
        processed.append(out)

    # 2. Concaténation simple
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # 3. Superposition des Textes & Logo (Synchronisation Millimétrée)
    # Style : Gros texte blanc, bordure noire épaisse (style TikTok Viral)
    draw_base = f"fontfile={FONT}:borderw=12:bordercolor=black:fontcolor=white:x=(w-text_w)/2"
    
    text_filters = []
    for i in range(num):
        t_start = i * dur_seg
        t_end = (i + 1) * dur_seg
        txt = texts[i % len(texts)]
        # Effet "Pop-in" : Le texte arrive à la frame 1 du clip
        text_filters.append(f"drawtext=text='{txt}':{draw_base}:fontsize=110:y=h/2:enable='between(t,{t_start},{t_end})'")

    # Logo permanent discret
    brand = f"drawtext=text='@LesCrados.ai':{draw_base}:fontsize=35:fontcolor=white@0.5:y=120:x=w-text_w-50"
    
    # 4. Finalisation avec Audio & Fade Out
    filters = ",".join(text_filters)
    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},{filters},fade=t=out:st={CFG['total_dur']-1}:d=1\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(final_cmd)
    print("✅ Montage corrigé et finalisé.")

if __name__ == "__main__":
    start()
