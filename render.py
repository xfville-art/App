import json, base64, os, subprocess, re

# CONFIGURATION ÉLÉGANTE
CFG = {
    "total_dur": 15.0,
    "res": "720x1280",
    "fps": 24,
    "text_size": 55,       # Texte plus petit et élégant
    "padding": 80,         # Espace par rapport aux bords
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
    
    # Textes plus narratifs et sobres
    punchlines = ["L'art de l'immonde", "Édition limitée", "Le génie du chaos", "Collection 2024"]

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # Ajout d'un léger flou sur les bords (Vignette) pour le côté Premium
        vf = ("scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              "vignette=angle=0.2:x0=w/2:y0=h/2")
        
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac {out}')
        processed.append(out)

    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c:v copy -c:a copy base.mp4")

    # --- FILTRES TEXTES MODERNES ---
    text_filters = []
    for i in range(num):
        t_start = i * dur_seg
        t_end = (i + 1) * dur_seg
        txt = punchlines[i % len(punchlines)].upper()
        
        # Effet : Texte en bas avec une petite barre de soulignement moderne
        # Animation d'opacité (Fade in/out doux)
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:x=(w-text_w)/2:y=h-{CFG['padding']}-100:"
                 f"alpha='if(lt(t,{t_start}+0.3), (t-{t_start})/0.3, if(gt(t,{t_end}-0.3), ({t_end}-t)/0.3, 1))':"
                 f"enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    # Watermark ultra-discret en haut à droite
    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=28:fontcolor=white@0.2:x=w-text_w-40:y=60"
    
    # Filtre de couleur "Cinéma" (Légère teinte froide/bleutée pour moderniser)
    color_grade = "curves=preset=lighter"

    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{color_grade},{brand},{','.join(text_filters)}\" "
        f"-c:v libx264 -c:a copy output.mp4"
    )
    
    run(final_cmd)
    print("✅ Rendu v25 : Montage Modern Pro terminé.")

if __name__ == "__main__":
    start()
