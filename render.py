import json, base64, os, subprocess

# CONFIGURATION TIKTOK/REELS
W, H = 720, 1280
FPS = 30
# Police standard sur GitHub Actions
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    print(f"▶ {cmd[:100]}...")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_dur(path):
    try:
        cmd = f'ffprobe -v quiet -print_format json -show_format "{path}"'
        res = run(cmd)
        return float(json.loads(res.stdout)['format']['duration'])
    except: return 0.0

def start():
    if not os.path.exists('p.json'):
        print("❌ p.json introuvable"); return
    
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction des vidéos
    raw_clips = []
    for i, v in enumerate(data.get('videos', [])):
        path = f"r{i}.mp4"
        with open(path, "wb") as fout: fout.write(base64.b64decode(v['data']))
        raw_clips.append(path)

    # 2. Montage des segments (3 segments de 2.5s)
    segments = []
    for i, p in enumerate(raw_clips[:3]):
        target_dur = 2.5
        seg_out = f"seg_{i}.mp4"
        
        # Effet Zoom Dynamique (Injection de valeur réelle pour éviter l'erreur)
        zoom_expr = f"1.0+0.15*t/{target_dur}"
        shake = ",crop=w=iw-40:h=ih-40:x='20+20*sin(2*PI*t*12)':y='20+20*cos(2*PI*t*15)'" if i == 2 else ""
        
        vf = f"scale=1280:2276,zoompan=z='{zoom_expr}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}{shake},format=yuv420p"
        
        run(f'ffmpeg -y -i "{p}" -t {target_dur} -vf "{vf}" -c:v libx264 -preset superfast -crf 18 -an "{seg_out}"')
        if os.path.exists(seg_out): segments.append(seg_out)

    # 3. Assemblage
    if not segments: return
    with open("list.txt", "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i list.txt -c copy "no_text.mp4"')

    # 4. Textes "Punchy" (Jaune et Blanc avec bordure noire pour le mode sombre)
    dur_total = get_dur("no_text.mp4")
    txt_vf = (f"drawtext=text='HOOK VIRAL':fontfile={FONT}:fontsize=90:fontcolor=yellow:borderw=6:bordercolor=black:x=(w-text_w)/2:y=200:enable='between(t,0,2)',"
              f"drawtext=text='REGARDE JUSQU AU BOUT':fontfile={FONT}:fontsize=60:fontcolor=white:borderw=6:bordercolor=black:x=(w-text_w)/2:y=h-300:enable='between(t,{dur_total-2.5},{dur_total})'")
    
    # Fusion finale avec l'audio du premier clip
    run(f'ffmpeg -y -i "no_text.mp4" -i "{raw_clips[0]}" -vf "{txt_vf}" -map 0:v -map 1:a -t {dur_total} -c:v libx264 -crf 18 -c:a aac -shortest "output.mp4"')

    if os.path.exists("output.mp4"): print("✅ TERMINÉ : output.mp4 prêt")

if __name__ == "__main__":
    start()
