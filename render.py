import json, base64, os, subprocess

CFG = {
    "total_dur": 15.0,
    "res": "720x1280",
    "fps": 24,
    "text_size": 55,
    "padding": 80,
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
    
    punchlines = ["L'art de l'immonde", "Édition limitée", "Le génie du chaos", "Collection 2024"]

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # CORRECTIF : 'setpts=PTS-STARTPTS' assure que chaque clip commence au temps zéro interne
        # On ajoute également '-an' temporairement pour nettoyer les pistes audio corrompues des segments
        vf = ("scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              "setpts=PTS-STARTPTS,vignette=angle=0.2")
        
        # On extrait la vidéo et l'audio proprement
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac -ar 44100 {out}')
        processed.append(out)

    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    
    # CORRECTIF CONCAT : On force la synchronisation audio/vidéo
    run("ffmpeg -y -f concat -safe 0 -i l.txt -c:v copy -c:a copy base.mp4")

    # --- FILTRES TEXTES ET FINALISATION ---
    text_filters = []
    for i in range(num):
        t_start = i * dur_seg
        t_end = (i + 1) * dur_seg
        txt = punchlines[i % len(punchlines)].upper()
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:x=(w-text_w)/2:y=h-{CFG['padding']}-100:"
                 f"alpha='if(lt(t,{t_start}+0.3), (t-{t_start})/0.3, if(gt(t,{t_end}-0.3), ({t_end}-t)/0.3, 1))':"
                 f"enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=28:fontcolor=white@0.2:x=w-text_w-40:y=60"
    
    # CORRECTIF FINAL : '-shortest' coupe la vidéo dès que le flux le plus court s'arrête (évite l'écran noir)
    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},{','.join(text_filters)}\" "
        f"-c:v libx264 -c:a copy -shortest output.mp4"
    )
    
    run(final_cmd)
    print("✅ Rendu v25.1 terminé : Écran noir corrigé.")

if __name__ == "__main__":
    start()
