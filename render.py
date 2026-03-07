import json, base64, os, subprocess, re

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
HOOK_TARGET  = 2.0   # durée cible du hook (secondes)
CORE_TARGET  = 3.0   # durée cible du core
PUNCH_TARGET = 3.0   # durée cible de la punchline
FLASH_FRAMES = 1     # nombre de frames blanches entre les segments
FPS_OUT      = 24    # framerate de sortie
W, H         = 720, 1280

VF_BASE = (
    f"scale={W}:{H}:force_original_aspect_ratio=increase,"
    f"crop={W}:{H},"
    f"fps={FPS_OUT},"
    f"setsar=1"
)

def run(cmd):
    print(f"▶ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[-400:]}")
    return result

def get_duration(path):
    """Retourne la durée exacte d'un fichier vidéo."""
    r = subprocess.run(
        f'ffprobe -v quiet -print_format json -show_format "{path}"',
        shell=True, capture_output=True, text=True
    )
    info = json.loads(r.stdout)
    return float(info['format']['duration'])

def find_best_cut(path, target_t, tolerance=0.6):
    """
    Cherche le meilleur point de coupe autour de target_t.
    Utilise ffmpeg scdet (scene change detection) pour trouver
    un vrai changement de scène dans la fenêtre [target_t - tol, target_t + tol].
    Si aucun n'est trouvé, retourne target_t.
    """
    dur = get_duration(path)
    t_min = max(0.3, target_t - tolerance)
    t_max = min(dur - 0.2, target_t + tolerance)

    # scdet sur la fenêtre autour du point cible
    r = subprocess.run(
        f'ffprobe -v quiet -read_intervals "%{t_min}%+{t_max - t_min}" '
        f'-show_frames -f lavfi '
        f'"movie={path},scdet=threshold=8" '
        f'-print_format json',
        shell=True, capture_output=True, text=True
    )

    candidates = []
    try:
        frames = json.loads(r.stdout).get('frames', [])
        for fr in frames:
            pts = float(fr.get('pkt_pts_time', fr.get('best_effort_timestamp_time', -1)))
            score = float(fr.get('tags', {}).get('lavfi.scd.score', 0))
            if t_min <= pts <= t_max and score > 0:
                candidates.append((pts, score))
    except Exception:
        pass

    if candidates:
        # Le meilleur score de changement de scène dans la fenêtre
        best = max(candidates, key=lambda x: x[1])
        print(f"  ✓ Cut naturel trouvé à {best[0]:.3f}s (score={best[1]:.1f}) vs cible {target_t}s")
        return best[0]
    else:
        print(f"  ~ Pas de cut naturel, utilisation de {target_t}s")
        return target_t

def make_flash(duration_s=0.042):
    """Génère un flash blanc d'une frame."""
    run(
        f'ffmpeg -y -f lavfi -i "color=c=white:size={W}x{H}:rate={FPS_OUT}" '
        f'-t {duration_s} -vf "setsar=1" -c:v libx264 -pix_fmt yuv420p flash.mp4'
    )

def trim_segment(src, out, duration, vf=VF_BASE):
    """Découpe et normalise un segment vidéo (sans audio)."""
    run(
        f'ffmpeg -y -i "{src}" -t {duration:.4f} '
        f'-vf "{vf}" '
        f'-c:v libx264 -preset fast -crf 18 '
        f'-an -pix_fmt yuv420p "{out}"'
    )

def concat_segments(segments, out):
    """Concatène une liste de fichiers vidéo via concat demuxer."""
    with open("list.txt", "w") as f:
        for s in segments:
            f.write(f"file '{s}'\n")
    run(
        f'ffmpeg -y -f concat -safe 0 -i list.txt '
        f'-c:v libx264 -crf 18 -preset fast '
        f'-pix_fmt yuv420p -movflags +faststart '
        f'-an "{out}"'
    )

def merge_audio(video, audio_src, out):
    """
    Mixe l'audio du clip source sur la vidéo finale.
    Tronque/étire l'audio pour matcher exactement la durée vidéo.
    """
    vid_dur = get_duration(video)
    run(
        f'ffmpeg -y -i "{video}" -i "{audio_src}" '
        f'-map 0:v -map 1:a '
        f'-t {vid_dur:.4f} '
        f'-c:v copy -c:a aac -b:a 128k '
        f'-af "afade=t=out:st={max(0, vid_dur-0.3):.3f}:d=0.3" '
        f'-movflags +faststart "{out}"'
    )

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def start():
    # 1. Chargement
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable")
        return

    with open('p.json', 'r') as f:
        data = json.load(f)

    videos = data.get('videos', [])
    n = len(videos)
    print(f"→ {n} clip(s) reçu(s)")

    # 2. Extraction
    raw = []
    for i, v in enumerate(videos):
        path = f"r{i}.mp4"
        with open(path, "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        dur = get_duration(path)
        print(f"  Clip {i} : {dur:.2f}s")
        raw.append((path, dur))

    # 3. Définir les durées cibles selon le nombre de clips
    if n == 1:
        targets = [HOOK_TARGET + CORE_TARGET + PUNCH_TARGET]
    elif n == 2:
        targets = [HOOK_TARGET, CORE_TARGET + PUNCH_TARGET]
    else:
        targets = [HOOK_TARGET, CORE_TARGET, PUNCH_TARGET]

    # 4. Trouver les meilleurs points de coupe et découper
    segments = []
    for i, ((path, dur), target) in enumerate(zip(raw, targets)):
        # Ne jamais dépasser la durée réelle du clip
        safe_target = min(target, dur - 0.1)
        cut_t = find_best_cut(path, safe_target)
        out = f"seg{i}.mp4"
        trim_segment(path, out, cut_t)
        segments.append(out)
        print(f"  Segment {i} : {cut_t:.3f}s")

    # 5. Flash entre les segments
    make_flash()
    interleaved = []
    for i, seg in enumerate(segments):
        interleaved.append(seg)
        if i < len(segments) - 1:
            interleaved.append("flash.mp4")

    # 6. Concaténation
    concat_segments(interleaved, "no_audio.mp4")

    # 7. Audio : prendre l'audio du clip le plus long (souvent le core ou punchline)
    audio_clip = max(raw, key=lambda x: x[1])[0]
    has_audio = subprocess.run(
        f'ffprobe -v quiet -select_streams a -show_streams "{audio_clip}"',
        shell=True, capture_output=True, text=True
    ).stdout.strip()

    if has_audio:
        merge_audio("no_audio.mp4", audio_clip, "output.mp4")
    else:
        # Pas d'audio — juste renommer
        os.rename("no_audio.mp4", "output.mp4")
        print("  (Pas d'audio dans les clips source)")

    # 8. Rapport final
    if os.path.exists("output.mp4"):
        final_dur = get_duration("output.mp4")
        print(f"\n✅ SUCCÈS : output.mp4 créé — {final_dur:.2f}s")
    else:
        print("\n❌ ÉCHEC : output.mp4 non généré")

if __name__ == "__main__":
    start()
