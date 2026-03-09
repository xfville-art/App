import json, base64, os, subprocess, urllib.request, re

CFG = {"total_dur": 25.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)

    # 1. Montage avec JUMP ZOOMS MODÉRÉS (Sans débordement)
    segs = []
    dur = CFG["total_dur"] / len(clips)
    # On reste entre 1.0 (taille réelle) et 1.15 (zoom léger) pour la sécurité
    zooms = ["1.0", "1.12", "1.05", "1.15"]
    
    for i, cp in enumerate(clips):
        out = f"s{i}.mp4"
        z = zooms[i % len(zooms)]
        # Utilisation de 'force_original_aspect_ratio=decrease' pour éviter le débordement
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,scale=iw*{z}:-1,crop=720:1280"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac s{i}.mp4')
        segs.append(out)

    with open("l.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # 2. Textes et Watermark @LesCrados.ai avec marges de sécurité
    # On baisse légèrement la taille de police pour éviter que ça touche les bords
    draw_main = f"fontfile={FONT}:borderw=10:bordercolor=black:x=(w-text_w)/2"
    draw_brand = f"fontfile={FONT}:fontsize=35:fontcolor=white@0.7:borderw=3:bordercolor=black@0.7:x=w-text_w-50:y=120"
    
    cmd_final = (
        f"ffmpeg -y -i base.mp4 -vf "
        f"\"drawtext=text='@LesCrados.ai':{draw_brand}, "
        f"drawtext=text='NE SWIPE PAS':{draw_main}:fontsize=100:fontcolor=white:y=280:enable='between(t,0,4)', "
        f"drawtext=text='C EST IMMONDE':{draw_main}:fontsize=90:fontcolor=yellow:y=h/2:enable='between(t,6,12)', "
        f"drawtext=text='LIKE ET COMMENTE':{draw_main}:fontsize=75:fontcolor=white:y=h-480:enable='between(t,15,20)', "
        f"drawtext=text='POUR LA SUITE':{draw_main}:fontsize=90:fontcolor=white:y=h-280:enable='between(t,21,25)'\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(cmd_final)
    print("✅ Rendu v13 terminé : Zoom corrigé et Watermark ajouté.")

if __name__ == "__main__":
    start()
