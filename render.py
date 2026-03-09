import json, base64, os, subprocess

# CONFIGURATION POUR UNE VIDÉO LONGUE ET PRO
CFG = {
    "res": "720x1280",
    "fps": 24,
    "text_size": 48,
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
    processed = []
    
    # Textes narratifs
    punchlines = ["EXPÉRIENCE INTERDITE", "MUTATION GÉNIALE", "L'ART DU PIRE", "COLLECTION 2026", "LE GÉNIE DU CHAOS"]

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # 🎨 ÉTALONNAGE & FLUIDITÉ
        # On ne met pas de limite '-t' ici pour garder TOUTE la durée du clip généré
        vf = (f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              f"fps={CFG['fps']},setpts=PTS-STARTPTS,unsharp=3:3:1.5,eq=saturation=1.2")
        
        # On traite le clip sans le couper
        run(f'ffmpeg -y -i {raw} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac -ar 44100 {out}')
        processed.append(out)

    # 🔗 CONCATÉNATION DE TOUS LES SEGMENTS
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -safe 0 -i l.txt -c:v copy -c:a copy combined.mp4")

    # 🏷️ AJOUT DES TEXTES ET WATERMARK SUR LA DURÉE TOTALE
    # On récupère d'abord la durée réelle du fichier combiné
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 combined.mp4")
    total_dur = float(res.stdout.strip())
    dur_per_txt = total_dur / num

    text_filters = []
    for i in range(num):
        t_start = i * dur_per_txt
        t_end = (i + 1) * dur_per_txt
        txt = punchlines[i % len(punchlines)]
        
        # Style moderne : Bas de l'écran, ombre portée, fondu
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=white:shadowcolor=black@0.6:shadowx=3:shadowy=3:"
                 f"x=(w-text_w)/2:y=h-200:"
                 f"alpha='if(lt(t,{t_start}+0.5), (t-{t_start})/0.5, if(gt(t,{t_end}-0.5), ({t_end}-t)/0.5, 1))':"
                 f"enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=24:fontcolor=white@0.2:x=w-text_w-40:y=60"
    
    # RENDU FINAL
    final_cmd = (
        f"ffmpeg -y -i combined.mp4 -vf \"{brand},{','.join(text_filters)}\" "
        f"-c:v libx264 -crf 18 -c:a copy -pix_fmt yuv420p output.mp4"
    )
    
    run(final_cmd)
    print(f"💎 Rendu v33 terminé. Durée totale : {total_dur:.2f}s")

if __name__ == "__main__":
    start()
