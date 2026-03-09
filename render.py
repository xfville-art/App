import json, base64, os, subprocess, urllib.request, re

CFG = {"total_dur": 25.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips_raw = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips_raw.append(p)

    # 1. Montage avec ZOOM ULTRA-LÉGER (Sécurité Max)
    segs = []
    num_clips = len(clips_raw)
    dur = CFG["total_dur"] / num_clips
    
    for i, cp in enumerate(clips_raw):
        out = f"s{i}.mp4"
        # Zoom quasi-imperceptible pour garder tout le personnage à l'écran
        z = "1.05" if i % 2 == 0 else "1.0"
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,scale=iw*{z}:-1,crop=720:1280"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac s{i}.mp4')
        segs.append(out)

    with open("l.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # 2. Textes Synchronisés sur les Scènes
    # On calcule les points de transition exacts pour que le texte change avec l'image
    t1, t2, t3 = dur, dur*2, dur*3
    
    draw_main = f"fontfile={FONT}:borderw=10:bordercolor=black:x=(w-text_w)/2"
    draw_brand = f"fontfile={FONT}:fontsize=35:fontcolor=white@0.7:x=w-text_w-50:y=120"
    
    # 3. FILTRE FINAL : Texte + Fondu de fin (Fade out)
    # L'effet 'fade' à la fin (d=1) évite la coupure brutale
    cmd_final = (
        f"ffmpeg -y -i base.mp4 -vf "
        f"\"drawtext=text='@LesCrados.ai':{draw_brand}, "
        f"drawtext=text='NE SWIPE PAS':{draw_main}:fontsize=95:fontcolor=white:y=280:enable='between(t,0,{t1})', "
        f"drawtext=text='C EST IMMONDE':{draw_main}:fontsize=85:fontcolor=yellow:y=h/2:enable='between(t,{t1},{t2})', "
        f"drawtext=text='LIKE ET COMMENTE':{draw_main}:fontsize=70:fontcolor=white:y=h-480:enable='between(t,{t2},{t3})', "
        f"drawtext=text='ABONNE-TOI':{draw_main}:fontsize=90:fontcolor=white:y=h-280:enable='between(t,{t3},{CFG['total_dur']})', "
        f"fade=t=out:st={CFG['total_dur']-1}:d=1\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(cmd_final)
    print(f"✅ Rendu v14 terminé. Synchro sur {dur:.2f}s par segment.")

if __name__ == "__main__":
    start()
