import json, base64, os, subprocess, urllib.request

# ─────────────────────────────────────────
#  CONFIG STABLE (720x1280 TikTok)
# ─────────────────────────────────────────
HOOK_DUR   = 2.2
CORE_DUR   = 2.2
PUNCH_DUR  = 3.2
FPS_OUT    = 30
W, H       = 720, 1280
# Chemin standard sur Ubuntu/GitHub Runner
FONT       = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")

def run(cmd, silent=False):
    if not silent: print(f"▶ {cmd[:100]}...")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and not silent:
        print(f"  ❌ Erreur FFmpeg : {r.stderr[-200:]}")
    return r

def get_duration(path):
    if not os.path.exists(path): return 0.0
    r = run(f'ffprobe -v quiet -print_format json -show_format "{path}"', silent=True)
    try:
        return float(json.loads(r.stdout)['format']['duration'])
    except: return 0.0

def apply_effects(src, out, is_punchline=False):
    dur = get_duration(src)
    if dur <= 0: dur = 2.0
    # Correction : Injection de la valeur numérique de la durée
    zoom_val = f"1.0+0.15*t/{dur}"
    shake = ",crop=w=iw-40:h=ih-40:x='20+20*sin(2*PI*t*12)':y='20+20*cos(2*PI*t*15)'" if is_punchline else ""
    
    vf = f"scale=1280:2276,zoompan=z='{zoom_val}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS_OUT}{shake},format=yuv420p"
    run(f'ffmpeg -y -i "{src}" -vf "{vf}" -c:v libx264 -preset superfast -crf 18 -an "{out}"')

def start():
    if not os.path.exists('p.json'):
        print("❌ Fichier p.json manquant"); return
    
    with open('p.json', 'r') as f: data = json.load(f)
    
    # 1. Extraction
    raw_clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        raw_clips.append(p)

    # 2. Montage des segments
    segments = []
    targets = [HOOK_DUR, CORE_DUR, PUNCH_DUR]
    for i, p in enumerate(raw_clips[:3]):
        tmp_p, final_s = f"pre_{i}.mp4", f"seg_{i}.mp4"
        run(f'ffmpeg -y -i "{p}" -t {targets[i]} -c:v libx264 -an "{tmp_p}"')
        apply_effects(tmp_p, final_s, is_punchline=(i == len(raw_clips[:3])-1))
        if os.path.exists(final_s): segments.append(final_s)

    # 3. Concaténation
    with open("list.txt", "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i list.txt -c copy "no_text.mp4"')

    # 4. Finalisation (Texte & Audio)
    dur_final = get_duration("no_text.mp4")
    if dur_final > 0:
        # Texte adapté au mode sombre (bordures noires épaisses)
        txt_filter = (f"drawtext=text='VIRACUT':fontfile={FONT}:fontsize=80:fontcolor=yellow:borderw=5:bordercolor=black:x=(w-text_w)/2:y=150:enable='between(t,0,2)',"
                      f"drawtext=text='ABONNE-TOI':fontfile={FONT}:fontsize=60:fontcolor=white:borderw=5:bordercolor=black:x=(w-text_w)/2:y=h-200:enable='between(t,{dur_final-2},{dur_final})'")
        
        run(f'ffmpeg -y -i "no_text.mp4" -i "{raw_clips[0]}" -vf "{txt_filter}" -map 0:v -map 1:a -t {dur_final} -c:v libx264 -crf 18 -c:a aac -shortest "output.mp4"')

    if os.path.exists("output.mp4"): print("✅ SUCCÈS : output.mp4 généré")
    else: print("❌ ÉCHEC : Rendu incomplet")

if __name__ == "__main__": start()
