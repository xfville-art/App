import json, base64, os, subprocess, urllib.request

# ─────────────────────────────────────────
#  CONFIG AMÉLIORÉE
# ─────────────────────────────────────────
HOOK_DUR   = 2.2
CORE_DUR   = 2.2
PUNCH_DUR  = 3.2
FPS_OUT    = 30 # Plus fluide pour TikTok
W, H       = 720, 1280
FONT       = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")

def run(cmd, silent=False):
    if not silent:
        print(f"▶ {cmd[:120]}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and not silent:
        print(f"  stderr: {r.stderr[-300:]}")
    return r

def get_duration(path):
    r = run(f'ffprobe -v quiet -print_format json -show_format "{path}"', silent=True)
    return float(json.loads(r.stdout)['format']['duration'])

def get_dimensions(path):
    r = run(f'ffprobe -v quiet -print_format json -show_streams "{path}"', silent=True)
    for s in json.loads(r.stdout).get('streams', []):
        if s.get('codec_type') == 'video':
            return int(s['width']), int(s['height'])
    return W, H

def get_scene_changes(path):
    r = run(f'ffprobe -v quiet -show_frames -f lavfi "movie={path},scdet=threshold=10" -print_format json', silent=True)
    changes = []
    try:
        for fr in json.loads(r.stdout).get('frames', []):
            score = float(fr.get('tags', {}).get('lavfi.scd.score', 0))
            pts   = float(fr.get('pkt_pts_time', 0))
            if score > 0 and pts > 0.2:
                changes.append((pts, score))
    except: pass
    return sorted(changes, key=lambda x: x[0])

# ─────────────────────────────────────────
#  IA : PROMPT VIRAL & TRASH
# ─────────────────────────────────────────
def extract_frame_b64(path):
    dur = get_duration(path)
    out = path + "_thumb.jpg"
    run(f'ffmpeg -y -ss {min(0.5, dur*0.2)} -i "{path}" -vframes 1 -q:v 2 "{out}"', silent=True)
    with open(out, "rb") as f:
        return base64.b64encode(f.read()).decode()

def generate_texts(clip_paths):
    if not API_KEY:
        return "C'EST TROP", "Il a pas osé 💀"

    print("  → Analyse IA (Style Viral/Trash)...")
    content = []
    for i, p in enumerate(clip_paths):
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": extract_frame_b64(p)}})
    
    content.append({"type": "text", "text": (
        "Tu es expert TikTok Viral pour une audience 'Shitposting' / Humour Noir. "
        "Génère un HOOK (3 mots max, MAJUSCULES) ultra-curiosité ou choc. "
        "Génère une PUNCHLINE (5 mots max) absurde ou insolente avec un emoji de fin. "
        "Pas de mots polis, utilise du jargon (POV, FRAUD, MASTERCLASS, CHAD). "
        "Réponds en JSON strict : {\"hook\": \"...\", \"punchline\": \"...\"}"
    )})

    payload = json.dumps({
        "model": "claude-3-5-sonnet-20240620",
        "max_tokens": 150,
        "messages": [{"role": "user", "content": content}]
    }).encode()

    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=payload,
        headers={"Content-Type": "application/json", "x-api-key": API_KEY, "anthropic-version": "2023-06-01"})
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            res = json.loads(data["content"][0]["text"])
            return res['hook'].upper(), res['punchline']
    except:
        return "C'EST TROP", "Il a pas osé 💀"

# ─────────────────────────────────────────
#  EFFETS VISUELS : SHAKE & ZOOM
# ─────────────────────────────────────────
def apply_advanced_effects(src, out, is_punchline=False):
    dur = get_duration(src)
    # 1. Zoom progressif constant (évite l'image statique)
    # 2. Camera Shake si c'est la punchline
    zoom_expr = "1.0+0.15*t/duration"
    shake = ""
    if is_punchline:
        shake = (f",crop=w=iw-40:h=ih-40:x='20+20*sin(2*PI*t*12)':y='20+20*cos(2*PI*t*15)'"
                 f",unsharp=3:3:1.2") # Plus net

    vf = (f"scale=1280:2276,zoompan=z='{zoom_expr}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS_OUT}{shake}")
    
    run(f'ffmpeg -y -i "{src}" -vf "{vf}" -c:v libx264 -preset superfast -crf 18 -an "{out}"')

def write_text_filter(hook, punchline, total_dur):
    pl_start = max(0, total_dur - 2.8)
    # Filtre avec animation de rebond (y) et couleur impact
    hook_f = (f"drawtext=text='{hook}':fontfile={FONT}:fontsize=95:fontcolor=yellow:borderw=8:bordercolor=black:"
              f"x=(w-text_w)/2:y=if(lt(t,0.3),-100+t*800,140):enable='between(t,0,2.3)'")
    
    pl_f = (f"drawtext=text='{punchline}':fontfile={FONT}:fontsize=70:fontcolor=white:borderw=8:bordercolor=black:"
            f"x=(w-text_w)/2:y=h-250:enable='between(t,{pl_start},{total_dur})'")
    
    with open("text_filter.txt", "w") as f: f.write(f"{hook_f},{pl_f}")

# ─────────────────────────────────────────
#  MONTAGE
# ─────────────────────────────────────────
def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Loading & Prep
    raw_clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        raw_clips.append(p)

    hook_txt, punch_txt = generate_texts(raw_clips)

    # 2. Processing segments
    segments = []
    targets = [HOOK_DUR, CORE_DUR, PUNCH_DUR]
    for i, p in enumerate(raw_clips[:3]):
        tmp_trim = f"tmp_{i}.mp4"
        is_punch = (i == len(raw_clips[:3]) - 1)
        
        # Trim simple d'abord
        run(f'ffmpeg -y -i "{p}" -t {targets[i]} -c:v libx264 -an "pre_{tmp_trim}"')
        # Applique Zoom + Shake
        apply_advanced_effects(f"pre_{tmp_trim}", tmp_trim, is_punchline=is_punch)
        segments.append(tmp_trim)

    # 3. Concat
    with open("list.txt", "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i list.txt -c copy "no_text.mp4"')

    # 4. Final Text & Audio
    dur_final = get_duration("no_text.mp4")
    write_text_filter(hook_txt, punch_txt, dur_final)
    
    # Merge Final avec Audio du premier clip et filtres texte
    audio_src = raw_clips[0]
    run(f'ffmpeg -y -i "no_text.mp4" -i "{audio_src}" -filter_script:v text_filter.txt '
        f'-map 0:v -map 1:a -t {dur_final} -c:v libx264 -crf 18 -c:a aac -shortest "output.mp4"')

    print(f"\n✅ TERMINÉ : {hook_txt} / {punch_txt}")

if __name__ == "__main__":
    start()
        
