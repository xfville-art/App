import json, base64, os, subprocess

# CONFIGURATION FINALE PRO
CFG = {
    "total_dur": 15.0,
    "res": "720x1280",
    "fps": 24,
    "text_size": 48,       # Taille optimale pour la lisibilité mobile
    "padding": 120,        # Plus d'espace en bas pour ne pas masquer le sujet
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
    
    # Textes courts et percutants (inspirés par l'univers Crados)
    punchlines = ["EXPÉRIENCE INTERDITE", "MUTATION GÉNIALE", "L'ART DU PIRE", "COLLECTION CRADOS"]

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # Filtre Pro : On ajoute une légère saturation et un contraste pour faire ressortir les couleurs
        # setpts=PTS-STARTPTS est maintenu pour éviter l'écran noir
        vf = ("scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              "setpts=PTS-STARTPTS,eq=saturation=1.2:contrast=1.1,vignette=angle=0.2")
        
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac -ar 44100 {out}')
        processed.append(out)

    # Concaténation propre
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -safe 0 -i l.txt -c:v copy -c:a copy base.mp4")

    # --- TITRAGE MODERNE ---
    text_filters = []
    for i in range(num):
        t_start = i * dur_seg
        t_end = (i + 1) * dur_seg
        txt = punchlines[i % len(punchlines)]
        
        # Style : Texte blanc pur avec une ombre portée légère pour la profondeur
        # Fondu entrant/sortant fluide de 0.2s
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:shadowcolor=black@0.5:shadowx=3:shadowy=3:"
                 f"x=(w-text_w)/2:y=h-{CFG['padding']}:"
                 f"alpha='if(lt(t,{t_start}+0.2), (t-{t_start})/0.2, if(gt(t,{t_end}-0.2), ({t_end}-t)/0.2, 1))':"
                 f"enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    # Watermark inspiré de l'UI ViraCut Studio
    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=24:fontcolor=white@0.15:x=w-text_w-30:y=50"
    
    # Rendu final avec synchronisation forcée (-shortest)
    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},{','.join(text_filters)}\" "
        f"-c:v libx264 -c:a copy -shortest output.mp4"
    )
    
    run(final_cmd)
    print("🔥 Montage v26 'Final Polish' terminé avec succès.")

if __name__ == "__main__":
    start()
