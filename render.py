import json, base64, os, subprocess, urllib.request, re

CFG = {"total_dur": 25.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def safe_txt(t):
    return re.sub(r"[^a-zA-Z0-9 !?À-ÿ]", "", t).strip().upper()

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)

    # 1. Rendu des Segments avec JUMP CUTS & FLASH BLANC
    segs = []
    dur = CFG["total_dur"] / len(clips)
    for i, cp in enumerate(clips):
        out = f"s{i}.mp4"
        z = [1.0, 1.25, 1.1, 1.3][i % 4]
        # On ajoute un fondu au blanc très court (0.2s) au début de chaque clip
        vf = f"scale=1280:1280,crop=720:1280,scale=iw*{z}:ih*{z},crop=720:1280,fade=t=in:st=0:d=0.2:color=white"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac s{i}.mp4')
        segs.append(out)

    with open("l.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # 2. Textes Dynamiques + Watermark @LesCrados.ai
    draw_main = f"fontfile={FONT}:borderw=12:bordercolor=black:x=(w-text_w)/2"
    # Style discret pour le watermark
    draw_brand = f"fontfile={FONT}:fontsize=40:fontcolor=white@0.6:borderw=4:bordercolor=black@0.6:x=w-text_w-40:y=100"
    
    # h = Hook / m = Milieu (avec léger tremblement Y) / p = Fin
    shake = "y=h/2+(7*sin(t*40))" 
    
    cmd_final = (
        f"ffmpeg -y -i base.mp4 -vf "
        f"\"drawtext=text='@LesCrados.ai':{draw_brand}, "
        f"drawtext=text='NE SWIPE PAS':{draw_main}:fontsize=115:fontcolor=white:y=280:enable='between(t,0,4)', "
        f"drawtext=text='C EST IMMONDE':{draw_main}:fontsize=100:fontcolor=yellow:{shake}:enable='between(t,6,12)', "
        f"drawtext=text='LIKE ET ABONNE-TOI':{draw_main}:fontsize=85:fontcolor=white:y=h-450:enable='between(t,15,20)', "
        f"drawtext=text='POUR LA SUITE':{draw_main}:fontsize=105:fontcolor=white:y=h-250:enable='between(t,21,25)'\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(cmd_final)
    print("✅ Rendu v12 terminé avec succès.")

if __name__ == "__main__":
    start()
