import json, base64, os, subprocess

CFG = {
    "total_dur": 15.0,
    "res": "720x1280",
    "fps": 24,
    "text_size": 55,
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
    
    punchlines = ["EXPÉRIENCE", "MUTATION", "CHAOS", "CRADOS 2026"]

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # SÉCURITÉ ANTI-ÉCRAN NOIR : 
        # On force la réinitialisation des timestamps (setpts) et on nettoie l'audio
        vf = (f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              f"setpts=PTS-STARTPTS,smartblur=1.5:-0.35:0,cas=0.5")
        
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 17 -c:a aac -ar 44100 {out}')
        processed.append(out)

    # Concaténation avec 'safe 0'
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -safe 0 -i l.txt -c:v copy -c:a copy base.mp4")

    # --- TEXT DESIGN ---
    text_filters = []
    for i in range(num):
        t_start = i * dur_seg
        t_end = (i + 1) * dur_seg
        txt = punchlines[i % len(punchlines)]
        f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize={CFG['text_size']}:"
                 f"fontcolor=yellow:borderw=10:bordercolor=black:"
                 f"x=(w-text_w)/2:y=h*0.75:"
                 f"alpha='if(lt(t,{t_start}+0.1), (t-{t_start})/0.1, if(gt(t,{t_end}-0.1), ({t_end}-t)/0.1, 1))':"
                 f"enable='between(t,{t_start},{t_end})'")
        text_filters.append(f_txt)

    brand = f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=26:fontcolor=white@0.2:x=w-text_w-40:y=60"
    
    # SÉCURITÉ FINALE : -shortest coupe le fichier si l'audio dépasse la vidéo
    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},{','.join(text_filters)}\" "
        f"-c:v libx264 -crf 18 -c:a copy -shortest -pix_fmt yuv420p output.mp4"
    )
    
    run(final_cmd)
    print("✅ Rendu v29.1 terminé. Écran noir corrigé.")

if __name__ == "__main__":
    start()
