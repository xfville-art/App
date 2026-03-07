import json, base64, os, subprocess, urllib.request

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
HOOK_DUR   = 2.0
CORE_DUR   = 2.5
PUNCH_DUR  = 3.0
FPS_OUT    = 24
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
        if s.get('codec_type') == 'video' and s.get('codec_name') != 'mjpeg':
            return int(s['width']), int(s['height'])
    return W, H

def get_scene_changes(path):
    r = run(f'ffprobe -v quiet -show_frames '
            f'-f lavfi "movie={path},scdet=threshold=10" '
            f'-print_format json', silent=True)
    changes = []
    try:
        for fr in json.loads(r.stdout).get('frames', []):
            score = float(fr.get('tags', {}).get('lavfi.scd.score', 0))
            pts   = float(fr.get('pkt_pts_time', fr.get('best_effort_timestamp_time', -1)))
            if score > 0 and pts > 0.2:
                changes.append((pts, score))
    except Exception:
        pass
    return sorted(changes, key=lambda x: x[0])

# ─────────────────────────────────────────
#  IA : analyse + génération textes
# ─────────────────────────────────────────
def extract_frame_b64(path):
    dur = get_duration(path)
    out = path + "_thumb.jpg"
    run(f'ffmpeg -y -ss {min(1.0, dur*0.3)} -i "{path}" -vframes 1 -q:v 3 "{out}"', silent=True)
    with open(out, "rb") as f:
        return base64.b64encode(f.read()).decode()

def generate_texts(clip_paths):
    if not API_KEY:
        print("  ⚠ ANTHROPIC_API_KEY absente — textes par défaut")
        return "TAS VU CA", "Impossible de pas rire"

    print("  → Analyse IA des clips...")
    content = []
    for i, p in enumerate(clip_paths):
        content.append({"type": "text", "text": f"Clip {i+1} :"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": extract_frame_b64(p)}
        })
    content.append({"type": "text", "text": (
        "Tu es expert TikTok viral pour une chaîne de cartes animées humoristiques "
        "style Garbage Pail Kids francophone.\n\n"
        "Analyse ces clips et génère :\n"
        "1. HOOK : max 4 mots, MAJUSCULES, choc/WTF/absurde, sans apostrophe ni deux-points\n"
        "2. PUNCHLINE : max 6 mots, humour décalé, sans apostrophe ni deux-points, "
        "peut finir par un seul emoji simple (pas de combinaisons)\n\n"
        "Réponds UNIQUEMENT en JSON strict sans markdown :\n"
        '{"hook": "TEXTE", "punchline": "Texte emoji"}'
    )})

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": content}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        raw = data["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
        result = json.loads(raw)
        hook = result.get("hook", "TAS VU CA").replace("'", " ").replace(":", " ")
        pl   = result.get("punchline", "Impossible de pas rire").replace("'", " ").replace(":", " ")
        print(f"  ✓ Hook      : {hook}")
        print(f"  ✓ Punchline : {pl}")
        return hook, pl
    except Exception as e:
        print(f"  ⚠ Erreur IA ({e}) — textes par défaut")
        return "TAS VU CA", "Impossible de pas rire"

# ─────────────────────────────────────────
#  TEXTES ANIMÉS via filter_script
# ─────────────────────────────────────────
def write_text_filter(hook, punchline, total_dur):
    """
    Écrit le filtre drawtext dans un fichier temporaire.
    Hook    : blanc, haut, slide depuis le haut, visible 0 → 2.5s
    Punchline : jaune, bas, slide depuis le bas, visible total_dur-2.5 → fin
    """
    pl_start = max(0, total_dur - 2.8)
    pl_end   = total_dur

    hook_filter = (
        f"drawtext="
        f"text='{hook}':"
        f"fontfile={FONT}:"
        f"fontsize=86:"
        f"fontcolor=white:"
        f"borderw=7:bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"y=if(lt(t\\,0.22)\\,50+t*636\\,190):"
        f"alpha=if(lt(t\\,0.22)\\,t/0.22\\,if(lt(t\\,2.2)\\,1\\,max(0\\,(2.5-t)/0.3))):"
        f"enable='between(t\\,0\\,2.5)'"
    )

    pl_filter = (
        f"drawtext="
        f"text='{punchline}':"
        f"fontfile={FONT}:"
        f"fontsize=62:"
        f"fontcolor=yellow:"
        f"borderw=7:bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"y=if(lt(t\\,{pl_start+0.25:.3f})\\,1400-(t-{pl_start:.3f})*1120\\,1120):"
        f"alpha=if(lt(t\\,{pl_start:.3f})\\,0\\,if(lt(t\\,{pl_start+0.25:.3f})\\,(t-{pl_start:.3f})/0.25\\,if(lt(t\\,{pl_end-0.3:.3f})\\,1\\,max(0\\,({pl_end:.3f}-t)/0.3)))):"
        f"enable='between(t\\,{pl_start:.3f}\\,{pl_end:.3f})'"
    )

    filt = f"{hook_filter},{pl_filter}"
    with open("text_filter.txt", "w") as f:
        f.write(filt)

def apply_text_overlay(src, out, hook, punchline):
    dur = get_duration(src)
    write_text_filter(hook, punchline, dur)
    r = run(f'ffmpeg -y -i "{src}" -filter_script:v text_filter.txt '
            f'-c:v libx264 -preset fast -crf 17 -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print("  ⚠ drawtext échoué — copie sans texte")
        run(f'cp "{src}" "{out}"')

# ─────────────────────────────────────────
#  MISE EN FORME + MONTAGE
# ─────────────────────────────────────────
def make_vf(src_w, src_h):
    src_ratio = src_w / src_h
    if src_ratio <= W / H + 0.05:
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1,fps={FPS_OUT}")
    else:
        scaled_h = int(src_h * W / src_w)
        if scaled_h % 2 != 0: scaled_h -= 1
        pad_y = (H - scaled_h) // 2
        return (f"scale={W}:{scaled_h},"
                f"pad={W}:{H}:0:{pad_y}:black,"
                f"setsar=1,fps={FPS_OUT}")

def score_as_hook(changes):
    early = [(t, s) for t, s in changes if t <= 2.5]
    return len(early) * 10 + sum(s for t, s in early)

def score_as_punchline(changes):
    late = [(t, s) for t, s in changes if t >= 3.0]
    return len(late) * 10 - len(changes) * 2

def classify_clips(clips):
    n = len(clips)
    if n == 1:
        return clips, [HOOK_DUR + CORE_DUR + PUNCH_DUR]
    if n == 2:
        s0 = score_as_hook(clips[0][2])
        s1 = score_as_hook(clips[1][2])
        ordered = [clips[0], clips[1]] if s0 >= s1 else [clips[1], clips[0]]
        return ordered, [HOOK_DUR, CORE_DUR + PUNCH_DUR]
    hook_scores  = [score_as_hook(c[2])      for c in clips]
    punch_scores = [score_as_punchline(c[2]) for c in clips]
    hi = hook_scores.index(max(hook_scores))
    rem = [i for i in range(n) if i != hi]
    pi = max(rem, key=lambda i: punch_scores[i])
    ci = [i for i in range(n) if i != hi and i != pi][0]
    print(f"  Ordre → hook=r{hi}  core=r{ci}  punchline=r{pi}")
    return [clips[hi], clips[ci], clips[pi]], [HOOK_DUR, CORE_DUR, PUNCH_DUR]

def best_cut(changes, target, dur, tol=0.7):
    window = [(t, s) for t, s in changes if abs(t - target) <= tol]
    if window:
        best = max(window, key=lambda x: x[1])
        print(f"  ✓ Cut naturel {best[0]:.3f}s (score {best[1]:.1f})")
        return best[0]
    safe = min(target, dur - 0.15)
    print(f"  ~ Coupe à {safe:.3f}s")
    return safe

def make_flash():
    run(f'ffmpeg -y -f lavfi -i "color=c=white:size={W}x{H}:rate={FPS_OUT}" '
        f'-t 0.042 -vf "setsar=1" -c:v libx264 -pix_fmt yuv420p flash.mp4')

def trim_segment(src, out, duration, vf):
    run(f'ffmpeg -y -i "{src}" -t {duration:.4f} -vf "{vf}" '
        f'-c:v libx264 -preset fast -crf 18 -an -pix_fmt yuv420p "{out}"')

def apply_zoom_punch(src, out, punch_t, seg_dur):
    fps     = FPS_OUT
    pf      = int(punch_t * fps)
    zi, zo  = 3, 6
    zoom_expr = (
        f"if(between(on,{pf},{pf+zi}),"
        f"1.0+(on-{pf})*0.08/{zi},"
        f"if(between(on,{pf+zi},{pf+zi+zo}),"
        f"1.08-(on-{pf+zi})*0.08/{zo},"
        f"1.0))"
    )
    vf = (f"zoompan=z='{zoom_expr}'"
          f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d=1:s={W}x{H}:fps={fps}")
    r = run(f'ffmpeg -y -i "{src}" -vf "{vf}" '
            f'-c:v libx264 -preset fast -crf 18 -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out):
        run(f'cp "{src}" "{out}"')

def concat_segments(segments, out):
    with open("list.txt", "w") as f:
        for s in segments:
            f.write(f"file '{s}'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i list.txt '
        f'-c:v libx264 -crf 18 -preset fast '
        f'-pix_fmt yuv420p -movflags +faststart -an "{out}"')

def merge_audio(video, audio_src, out):
    vid_dur = get_duration(video)
    run(f'ffmpeg -y -i "{video}" -i "{audio_src}" '
        f'-map 0:v -map 1:a -t {vid_dur:.4f} '
        f'-c:v copy -c:a aac -b:a 128k '
        f'-af "afade=t=out:st={max(0,vid_dur-0.4):.3f}:d=0.4" '
        f'-movflags +faststart "{out}"')

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def start():
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable"); return

    with open('p.json', 'r') as f:
        data = json.load(f)

    videos = data.get('videos', [])
    n = len(videos)
    print(f"→ {n} clip(s) reçu(s)")

    # 1. Extraction + analyse
    raw = []
    for i, v in enumerate(videos):
        path = f"r{i}.mp4"
        with open(path, "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        dur     = get_duration(path)
        w, h    = get_dimensions(path)
        changes = get_scene_changes(path)
        print(f"  Clip r{i}: {dur:.2f}s  {w}x{h}  {len(changes)} changements")
        raw.append((path, dur, changes, w, h))

    # 2. Ordre narratif
    clips_for_order = [(p, d, c) for p, d, c, w, h in raw]
    ordered, durations = classify_clips(clips_for_order)
    ordered_full = []
    for op, od, oc in ordered:
        for p, d, c, w, h in raw:
            if p == op:
                ordered_full.append((p, d, c, w, h)); break

    # 3. Textes IA
    all_paths = [p for p, d, c, w, h in ordered_full]
    hook_text, punch_text = generate_texts(all_paths)

    # 4. Découpe + zoom punch
    make_flash()
    segments = []
    for i, ((path, dur, changes, w, h), target) in enumerate(zip(ordered_full, durations)):
        cut_t   = best_cut(changes, target, dur)
        vf      = make_vf(w, h)
        raw_seg = f"raw_seg{i}.mp4"
        trim_segment(path, raw_seg, cut_t, vf)

        seg_out = f"seg{i}.mp4"
        if i == 1 and changes:
            in_seg = [(t, s) for t, s in changes if 0.3 < t < cut_t]
            if in_seg:
                pt = max(in_seg, key=lambda x: x[1])[0]
                print(f"  → Zoom punch à {pt:.3f}s")
                apply_zoom_punch(raw_seg, seg_out, pt, cut_t)
            else:
                run(f'cp "{raw_seg}" "{seg_out}"', silent=True)
        else:
            run(f'cp "{raw_seg}" "{seg_out}"', silent=True)

        segments.append(seg_out)
        print(f"  Segment {i} → {get_duration(seg_out):.3f}s")

    # 5. Concat avec flash
    interleaved = []
    for i, seg in enumerate(segments):
        interleaved.append(seg)
        if i < len(segments) - 1:
            interleaved.append("flash.mp4")
    concat_segments(interleaved, "no_text.mp4")

    # 6. Textes animés
    print(f"  → Textes : '{hook_text}' / '{punch_text}'")
    apply_text_overlay("no_text.mp4", "no_audio.mp4", hook_text, punch_text)

    # 7. Audio
    audio_clip = None
    for path, dur, changes, w, h in raw:
        if run(f'ffprobe -v quiet -select_streams a -show_streams "{path}"',
               silent=True).stdout.strip():
            audio_clip = path; break

    if audio_clip:
        merge_audio("no_audio.mp4", audio_clip, "output.mp4")
    else:
        os.rename("no_audio.mp4", "output.mp4")

    # 8. Rapport
    if os.path.exists("output.mp4"):
        fd = get_duration("output.mp4")
        fw, fh = get_dimensions("output.mp4")
        print(f"\n✅ SUCCÈS : output.mp4  {fw}x{fh}  {fd:.2f}s")
        print(f"   Hook      : {hook_text}")
        print(f"   Punchline : {punch_text}")
    else:
        print("\n❌ ÉCHEC : output.mp4 non généré")

if __name__ == "__main__":
    start()
