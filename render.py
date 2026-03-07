import json, base64, os, subprocess, urllib.request

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
HOOK_DUR   = 2.2
CORE_DUR   = 2.2
PUNCH_DUR  = 3.2
FPS_OUT    = 30
W, H       = 720, 1280
FONT       = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")

def run(cmd, silent=False):
    if not silent:
        print(f"▶ {cmd[:120]}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and not silent:
        print(f"  ❌ FFmpeg Error: {r.stderr[-500:]}")
    return r

def get_duration(path):
    if not os.path.exists(path): return 0.0
    r = run(f'ffprobe -v quiet -print_format json -show_format "{path}"', silent=True)
    try:
        data = json.loads(r.stdout)
        return float(data.get('format', {}).get('duration', 0))
    except: return 0.0

# ─────────────────────────────────────────
#  IA & TEXTES (Version simplifiée pour stabilité)
# ─────────────────────────────────────────
def generate_texts():
    # Pour le debug ou si API absente
    return "C EST TROP", "Il a pas osé 💀"

# ─────────────────────────────────────────
#  EFFETS VISUELS CORRIGÉS
# ─────────────────────────────────────────
def apply_advanced_effects(src, out, is_punchline=False):
    dur = get_duration(src)
    if dur <= 0:
        print(f"  ⚠ Fichier source invalide: {src}")
        return
    
    # Correction : on injecte la valeur de dur directement
    # car 'duration' n'est pas une variable interne de zoompan
    zoom_expr = f"1.0+0.15*t/{dur}"
    shake = ""
    if is_punchline:
        shake = (f",crop=w=iw-40:h=ih-40:x='20+20*sin(2*PI*t*12)':y='20+20*cos(2*PI*t*15)'"
                 f",unsharp=3:3:1.2")

    # On force une résolution intermédiaire élevée pour le zoompan (évite le flou/jitter)
    vf = (f"scale=1280:2276,zoompan=z='{zoom_expr}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS_OUT}{shake}")
    
    run(f'ffmpeg -y -i "{src}" -vf "{vf}" -c:v libx264 -preset superfast -crf 18 -an "{out}"')

def write_text_filter(hook, punchline, total_dur):
    pl_start = max(0, total_dur - 2.8)
    hook_f = (f"drawtext=text='{hook}':fontfile={FONT}:fontsize=95:fontcolor=yellow:borderw=8:bordercolor=black:"
              f"x=(w-text_w)/2:y=if(lt(t,0.3),-100+t*800,140):enable='between(t,0,2.3)'")
    pl_f = (f"drawtext=text='{punchline}':fontfile={FONT}:fontsize=70:fontcolor=white:borderw=8:bordercolor=black:"
            f"x=(w-text_w)/2:y=h-250:enable='between(t,{pl_start},{total_dur})'")
    with open("text_filter.txt", "w") as f: f.write(f"{hook_f},{pl_f}")

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def start():
    # Vérification du p.json
    if not os.path.exists('p.json'):
        print("Fichier p.json manquant")
        return
    
    with open('p.json', 'r') as f: data = json.load(f)

    raw_clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        raw_clips.append(p)

    if not raw_clips: return

    hook_txt, punch_txt = generate_texts()
    segments = []
    targets = [HOOK_DUR, CORE_DUR, PUNCH_DUR]

    for i, p in enumerate(raw_clips[:3]):
        pre_trim = f"pre_tmp_{i}.mp4"
        final_seg = f"tmp_{i}.mp4"
        is_punch = (i == len(raw_clips[:3]) - 1)
        
        # 1. Trim
        run(f'ffmpeg -y -i "{p}" -t {targets[i]} -c:v libx264 -preset superfast -an "{pre_trim}"')
        
        # 2. Effets (Zoom / Shake)
        apply_advanced_effects(pre_trim, final_seg, is_punchline=is_punch)
        
        if os.path.exists(final_seg):
            segments.append(final_seg)

    # 3. Concaténation
    if not segments: return
    with open("list.txt", "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
    
    run(f'ffmpeg -y -f concat -safe 0 -i list.txt -c copy "no_text.mp4"')

    # 4. Finalisation
    dur_final = get_duration("no_text.mp4")
    if dur_final == 0:
        print("Erreur : no_text.mp4 est vide ou corrompu")
        return

    write_text_filter(hook_txt, punch_txt, dur_final)
    audio_src = raw_clips[0]
    
    run(f'ffmpeg -y -i "no_text.mp4" -i "{audio_src}" -filter_script:v text_filter.txt '
        f'-map 0:v -map 1:a -t {dur_final} -c:v libx264 -crf 18 -c:a aac -shortest "output.mp4"')

    if os.path.exists("output.mp4"):
        print(f"\n✅ SUCCÈS : output.mp4 créé")

if __name__ == "__main__":
    start()
