import json, base64, os, subprocess, re

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
HOOK_DUR   = 2.0   # durée hook
CORE_DUR   = 2.5   # durée core
PUNCH_DUR  = 3.0   # durée punchline (prendre plus de la fin)
FPS_OUT    = 24
W, H       = 720, 1280

def run(cmd, silent=False):
    if not silent:
        print(f"▶ {cmd[:120]}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0 and not silent:
        print(f"  stderr: {result.stderr[-300:]}")
    return result

def get_duration(path):
    r = run(f'ffprobe -v quiet -print_format json -show_format "{path}"', silent=True)
    return float(json.loads(r.stdout)['format']['duration'])

def get_scene_changes(path):
    """
    Retourne la liste des timestamps de changements de scène détectés.
    Utilise le filtre scdet directement sur le fichier.
    """
    r = run(
        f'ffprobe -v quiet -show_frames '
        f'-f lavfi "movie={path},scdet=threshold=10" '
        f'-print_format json',
        silent=True
    )
    changes = []
    try:
        frames = json.loads(r.stdout).get('frames', [])
        for fr in frames:
            score = float(fr.get('tags', {}).get('lavfi.scd.score', 0))
            pts = float(fr.get('pkt_pts_time', fr.get('best_effort_timestamp_time', -1)))
            if score > 0 and pts > 0.2:
                changes.append((pts, score))
    except Exception:
        pass
    return sorted(changes, key=lambda x: x[0])

def score_as_hook(path, dur, changes):
    """
    Score d'un clip pour être le hook.
    Critères : changement de scène tôt (≤ 2s), début dynamique.
    """
    score = 0
    # Changement de scène tôt = bon hook
    early = [t for t, s in changes if t <= 2.5]
    score += len(early) * 10
    # Durée suffisante
    if dur >= 4.0:
        score += 5
    return score

def score_as_punchline(path, dur, changes):
    """
    Score d'un clip pour être la punchline.
    Critères : changement de scène tard (≥ 3s), fin impactante.
    """
    score = 0
    late = [t for t, s in changes if t >= 3.0]
    score += len(late) * 10
    # Peu de changements = plan posé = bonne punchline
    if len(changes) <= 2:
        score += 8
    return score

def classify_clips(clips):
    """
    Reçoit une liste de (path, dur, changes).
    Retourne (hook, core, punchline) dans le bon ordre.
    """
    n = len(clips)
    if n == 1:
        return clips, [HOOK_DUR + CORE_DUR + PUNCH_DUR]
    if n == 2:
        # Le clip avec le + de changements tôt = hook
        s0 = score_as_hook(clips[0][0], clips[0][1], clips[0][2])
        s1 = score_as_hook(clips[1][0], clips[1][1], clips[1][2])
        if s0 >= s1:
            return [clips[0], clips[1]], [HOOK_DUR, CORE_DUR + PUNCH_DUR]
        else:
            return [clips[1], clips[0]], [HOOK_DUR, CORE_DUR + PUNCH_DUR]

    # 3 clips : trouver hook et punchline, le reste = core
    hook_scores  = [score_as_hook(p, d, c)      for p, d, c in clips]
    punch_scores = [score_as_punchline(p, d, c) for p, d, c in clips]

    hook_idx  = hook_scores.index(max(hook_scores))
    # Punchline parmi les clips restants
    remaining = [i for i in range(n) if i != hook_idx]
    punch_idx = max(remaining, key=lambda i: punch_scores[i])
    core_idx  = [i for i in range(n) if i != hook_idx and i != punch_idx][0]

    print(f"  Ordre détecté → hook={hook_idx}  core={core_idx}  punchline={punch_idx}")
    print(f"  Scores hook:  {hook_scores}")
    print(f"  Scores punch: {punch_scores}")

    ordered = [clips[hook_idx], clips[core_idx], clips[punch_idx]]
    return ordered, [HOOK_DUR, CORE_DUR, PUNCH_DUR]

def best_cut(changes, target, dur, tol=0.7):
    """Trouve le cut naturel le plus proche de target dans ±tol."""
    window = [(t, s) for t, s in changes if abs(t - target) <= tol]
    if window:
        best = max(window, key=lambda x: x[1])
        print(f"  ✓ Cut naturel {best[0]:.3f}s (score {best[1]:.1f}) vs cible {target}s")
        return best[0]
    safe = min(target, dur - 0.15)
    print(f"  ~ Pas de cut naturel, coupe à {safe:.3f}s")
    return safe

def make_vf(src_w, src_h):
    """
    Construit le filtre vidéo adapté au ratio source.
    - Si source est 9:16 (vertical) → scale + crop simple
    - Si source est 4:3 ou 16:9 (horizontal/carré) → pillarbox + fond noir
    """
    src_ratio = src_w / src_h
    target_ratio = W / H  # 9/16 = 0.5625

    if src_ratio <= 0.6:
        # Déjà vertical (9:16 ou proche) → juste scaler
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS_OUT}"
    else:
        # Horizontal ou carré → scale pour remplir la hauteur, pad pour les côtés
        vf = (
            f"scale=-2:{H},"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps={FPS_OUT}"
        )
    return vf

def get_dimensions(path):
    r = run(f'ffprobe -v quiet -print_format json -show_streams "{path}"', silent=True)
    for s in json.loads(r.stdout).get('streams', []):
        if s.get('codec_type') == 'video' and s.get('codec_name') != 'mjpeg':
            return int(s['width']), int(s['height'])
    return 720, 1280

def trim_segment(src, out, duration, vf):
    run(
        f'ffmpeg -y -i "{src}" -t {duration:.4f} '
        f'-vf "{vf}" '
        f'-c:v libx264 -preset fast -crf 18 '
        f'-an -pix_fmt yuv420p "{out}"'
    )

def make_flash():
    run(
        f'ffmpeg -y -f lavfi '
        f'-i "color=c=white:size={W}x{H}:rate={FPS_OUT}" '
        f'-t 0.042 -vf "setsar=1" -c:v libx264 -pix_fmt yuv420p flash.mp4'
    )

def concat_segments(segments, out):
    with open("list.txt", "w") as f:
        for s in segments:
            f.write(f"file '{s}'\n")
    run(
        f'ffmpeg -y -f concat -safe 0 -i list.txt '
        f'-c:v libx264 -crf 18 -preset fast '
        f'-pix_fmt yuv420p -movflags +faststart -an "{out}"'
    )

def merge_audio(video, audio_src, out):
    vid_dur = get_duration(video)
    run(
        f'ffmpeg -y -i "{video}" -i "{audio_src}" '
        f'-map 0:v -map 1:a '
        f'-t {vid_dur:.4f} '
        f'-c:v copy -c:a aac -b:a 128k '
        f'-af "afade=t=out:st={max(0, vid_dur - 0.4):.3f}:d=0.4" '
        f'-movflags +faststart "{out}"'
    )

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def start():
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable")
        return

    with open('p.json', 'r') as f:
        data = json.load(f)

    videos = data.get('videos', [])
    n = len(videos)
    print(f"→ {n} clip(s) reçu(s)")

    # 1. Extraction
    raw_paths = []
    for i, v in enumerate(videos):
        path = f"r{i}.mp4"
        with open(path, "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        dur = get_duration(path)
        w, h = get_dimensions(path)
        changes = get_scene_changes(path)
        print(f"  Clip {i}: {dur:.2f}s  {w}x{h}  {len(changes)} changements de scène")
        raw_paths.append((path, dur, changes, w, h))

    # 2. Classification et ordre narratif
    clips_for_order = [(p, d, c) for p, d, c, w, h in raw_paths]
    ordered, durations = classify_clips(clips_for_order)

    # Retrouver les dimensions pour chaque clip ordonné
    ordered_full = []
    for op, od, oc in ordered:
        for p, d, c, w, h in raw_paths:
            if p == op:
                ordered_full.append((p, d, c, w, h))
                break

    # 3. Découpe intelligente
    make_flash()
    segments = []
    for i, ((path, dur, changes, w, h), target) in enumerate(zip(ordered_full, durations)):
        cut_t = best_cut(changes, target, dur)
        vf = make_vf(w, h)
        out = f"seg{i}.mp4"
        trim_segment(path, out, cut_t, vf)
        actual = get_duration(out)
        print(f"  Segment {i} → {actual:.3f}s  (recadrage {'pad' if w/h > 0.6 else 'crop'})")
        segments.append(out)

    # 4. Interleave flash + concat
    interleaved = []
    for i, seg in enumerate(segments):
        interleaved.append(seg)
        if i < len(segments) - 1:
            interleaved.append("flash.mp4")

    concat_segments(interleaved, "no_audio.mp4")

    # 5. Audio : prendre le clip source avec la meilleure durée audio
    audio_clip = None
    for path, dur, changes, w, h in raw_paths:
        has_audio = run(
            f'ffprobe -v quiet -select_streams a -show_streams "{path}"',
            silent=True
        ).stdout.strip()
        if has_audio:
            audio_clip = path
            break

    if audio_clip:
        merge_audio("no_audio.mp4", audio_clip, "output.mp4")
    else:
        os.rename("no_audio.mp4", "output.mp4")
        print("  (Pas d'audio détecté dans les clips)")

    # 6. Rapport
    if os.path.exists("output.mp4"):
        final_dur = get_duration("output.mp4")
        fw, fh = get_dimensions("output.mp4")
        print(f"\n✅ SUCCÈS : output.mp4  {fw}x{fh}  {final_dur:.2f}s")
    else:
        print("\n❌ ÉCHEC : output.mp4 non généré")

if __name__ == "__main__":
    start()
