import json, base64, os, subprocess, re

CFG = {"total_dur": 25.0, "res": "720:1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips_data = data.get('videos', [])
    num_clips = len(clips_data)
    dur = CFG["total_dur"] / num_clips
    
    segments = []
    text_filters = []
    
    # Textes ultra-punchy (adaptés à l'ambiance Crados/Steampunk)
    punchlines = [
        {"t": "TROP BIZARRE", "c": "white"},
        {"t": "INCROYABLE !", "c": "yellow"},
        {"t": "T'ES PRÊT ?", "c": "#00FF00"},
        {"t": "ABONNE-TOI", "c": "white"}
    ]

    for i, v in enumerate(clips_data):
        raw_p = f"r{i}.mp4"
        with open(raw_p, "wb") as f: f.write(base64.b64decode(v['data']))
        
        # Segment 100% FIXE (Sans zoom)
        out_p = f"s{i}.mp4"
        vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        run(f'ffmpeg -y -i {raw_p} -t {dur} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac {out_p}')
        segments.append(out_p)

        # Filtre de texte "Vivant" (vibration légère et ombre portée)
        start_t = i * dur
        end_t = (i + 1) * dur
        line = punchlines[i % len(punchlines)]
        
        # Effet de légère vibration sur Y pour donner de la vie
        shake = f"h/2-50+(10*sin(t*15))"
        
        draw = (
            f"drawtext=text='{line['t']}':fontfile={FONT}:fontsize=110:fontcolor={line['c']}:"
            f"borderw=12:bordercolor=black:x=(w-text_w)/2:y={shake}:"
            f"enable='between(t,{start_t},{end_t})'"
        )
        text_filters.append(draw)

    # Assemblage
    with open("l.txt", "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # Finalisation : Textes + Watermark + Fade Out
    filters = ",".join(text_filters)
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=35:fontcolor=white@0.5:x=w-text_w-50:y=120"
    
    cmd_final = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},{filters},fade=t=out:st={CFG['total_dur']-1}:d=1\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(cmd_final)
    print("✅ Rendu v16 : Fixe & Punchy !")

if __name__ == "__main__":
    start()
