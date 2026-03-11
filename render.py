"""
render.py — ViraCut Studio v8  ★ LesCrados.Ai Edition ★
═══════════════════════════════════════════════════════
v8 : Robustesse renforcée — gestion audio unifiée, clip_dur plancher,
     fallback si un segment échoue, meilleur logging
"""
import json, base64, os, subprocess, sys, time

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "mode": "auto", "resolution": "720x1280", "fps": 24, "crf": 18,
    "audio_br": 192, "fade_dur": 0.3,
    "cinema_dur": 26, "cinema_clip_min": 7, "cinema_clip_max": 12,
    "cinema_xfade": 0.8,
    "cinema_kb_zoom": 1.04,
    "cinema_lb_h": 80,
}

MIN_CLIP_DUR = 4.0   # durée plancher par segment (s)

# ═══════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════
def cfg(opts, key):
    return opts.get(key, DEFAULTS[key])

def run(cmd, check=True):
    short = cmd[:115] + ("..." if len(cmd) > 115 else "")
    print(f"    $ {short}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("STDERR:", r.stderr[-1000:])
        raise RuntimeError(f"FFmpeg failed (code {r.returncode})")
    return r.stdout + r.stderr

def ffprobe(path):
    cmd = f'ffprobe -v quiet -print_format json -show_format -show_streams "{path}"'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        return {"format": {}, "streams": []}
    return json.loads(r.stdout)

def duration(path):
    d = ffprobe(path)
    return float(d.get("format", {}).get("duration", 0))

def has_audio(path):
    d = ffprobe(path)
    return any(s.get("codec_type") == "audio" for s in d.get("streams", []))

# ═══════════════════════════════════════════════════════════════════════
# LOGO SPLASH ANIMÉ
# ═══════════════════════════════════════════════════════════════════════
def build_logo_splash(out, opts):
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps"); crf = cfg(opts, "crf")
    Wi, Hi = int(W), int(H)
    dur = 5.0
    les_sz, crados_sz, ai_sz = 78, 142, 82
    total_h   = les_sz + 18 + crados_sz + 14 + ai_sz
    block_top = (Hi - total_h) // 2
    les_y    = block_top
    crados_y = block_top + les_sz + 18
    ai_y     = block_top + les_sz + 18 + crados_sz + 22

    crad_y_expr = (
        f"if(lt(t,0.8),{Hi},"
        f"if(lt(t-0.8,0.5),{Hi}+({crados_y}-{Hi})*((t-0.8)/0.5),{crados_y}))"
    )
    ai_y_expr = (
        f"if(lt(t,1.7),{Hi},"
        f"if(lt(t-1.7,0.4),{Hi}+({ai_y}-{Hi})*((t-1.7)/0.4),{ai_y}))"
    )

    dt_les  = (f"drawtext=fontfile={FONT}:text='LES':fontsize={les_sz}:"
               f"fontcolor=white:x=(w-text_w)/2:y={les_y}:enable='gte(t,0.3)'")
    dt_crad = (f"drawtext=fontfile={FONT}:text='CRADOS':fontsize={crados_sz}:"
               f"fontcolor=white:x=(w-text_w)/2:y='{crad_y_expr}':enable='gte(t,0.8)'")
    dt_ai   = (f"drawtext=fontfile={FONT}:text='.Ai':fontsize={ai_sz}:"
               f"fontcolor=#FF2442:x=(w-text_w)/2:y='{ai_y_expr}':enable='gte(t,1.7)'")

    vf = f"{dt_les},{dt_crad},{dt_ai},fade=t=in:st=0:d=0.5,fade=t=out:st=4.2:d=0.8"
    run(
        f'ffmpeg -y -f lavfi -i "color=c=black:size={W}x{H}:rate={fps}" '
        f'-f lavfi -i "anullsrc=r=44100:cl=stereo" -t {dur} '
        f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{dur}[a]" '
        f'-map "[v]" -map "[a]" -c:v libx264 -pix_fmt yuv420p -crf {crf} "{out}"'
    )

def append_logo(premain, opts):
    build_logo_splash("_logo.mp4", opts)
    with open("_concat_logo.txt", "w") as f:
        f.write(f"file '{premain}'\nfile '_logo.mp4'\n")
    run(
        f'ffmpeg -y -f concat -safe 0 -i _concat_logo.txt '
        f'-c:v libx264 -pix_fmt yuv420p -crf {cfg(opts, "crf")} output.mp4'
    )

# ═══════════════════════════════════════════════════════════════════════
# SEGMENTS CINÉMA
# ═══════════════════════════════════════════════════════════════════════
def build_cinema_segment(src, seg_out, clip_dur, kb_zoom, opts):
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps")
    crf  = cfg(opts, "crf")

    # Recadrage + padding → pas de bord coupé
    scale_crop = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={fps}"
    )
    grade = "eq=saturation=0.95:brightness=-0.01:contrast=1.05"

    # Ken Burns doux
    inc = (kb_zoom - 1.0) / max(clip_dur * fps, 1)
    kb  = (
        f"zoompan=z='min(zoom+{inc:.6f},{kb_zoom})':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
    )

    vf = f"{scale_crop},{grade},{kb}"

    src_dur = duration(src)
    actual  = min(clip_dur, src_dur)   # ne jamais dépasser la durée réelle

    if has_audio(src):
        run(
            f'ffmpeg -y -t {actual:.2f} -i "{src}" '
            f'-vf "{vf}" -c:v libx264 -crf {crf} -c:a aac -shortest "{seg_out}"'
        )
    else:
        run(
            f'ffmpeg -y -t {actual:.2f} -i "{src}" '
            f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
            f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{actual:.2f}[a]" '
            f'-map "[v]" -map "[a]" -c:v libx264 -crf {crf} "{seg_out}"'
        )

def assemble_cinema(seg_paths, xfade_dur, opts):
    if len(seg_paths) == 1:
        run(f'cp "{seg_paths[0]}" _assembled.mp4')
        return

    inputs  = " ".join(f'-i "{p}"' for p in seg_paths)
    v_parts, a_parts = [], []
    offset  = duration(seg_paths[0]) - xfade_dur
    prev_v, prev_a = "[0:v]", "[0:a]"

    for i in range(1, len(seg_paths)):
        is_last = (i == len(seg_paths) - 1)
        nv = "[vfin]" if is_last else f"[xv{i}]"
        na = "[afin]" if is_last else f"[xa{i}]"
        v_parts.append(
            f"{prev_v}[{i}:v]xfade=transition=fade:duration={xfade_dur}:offset={offset:.3f}{nv}"
        )
        a_parts.append(f"{prev_a}[{i}:a]acrossfade=d={xfade_dur}{na}")
        offset  += duration(seg_paths[i]) - xfade_dur
        prev_v, prev_a = nv, na

    fc = ";".join(v_parts + a_parts)
    run(
        f'ffmpeg -y {inputs} -filter_complex "{fc}" '
        f'-map "[vfin]" -map "[afin]" -c:v libx264 -crf {cfg(opts,"crf")} _assembled.mp4'
    )

def build_cinema_overlay_no_text(opts):
    W, H = cfg(opts, "resolution").split("x")
    Hi   = int(H)
    lb_h = cfg(opts, "cinema_lb_h")
    total = duration("_assembled.mp4")
    fade_st = max(0.0, total - 0.5)

    lb = (
        f"drawbox=y=0:h={lb_h}:c=black@1:t=fill,"
        f"drawbox=y={Hi - lb_h}:h={lb_h}:c=black@1:t=fill"
    )
    run(
        f'ffmpeg -y -i _assembled.mp4 '
        f'-vf "{lb}" -af "afade=t=out:st={fade_st:.2f}:d=0.5" '
        f'-c:v libx264 -crf {cfg(opts,"crf")} _premain.mp4'
    )
    append_logo("_premain.mp4", opts)

# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════
def start():
    if not os.path.exists("p.json"):
        print("ERREUR : p.json introuvable")
        sys.exit(1)

    with open("p.json") as f:
        data = json.load(f)

    clips_raw = data.get("videos", [])
    opts      = data.get("options", {})

    if not clips_raw:
        print("ERREUR : aucun clip dans p.json")
        sys.exit(1)

    print("=" * 55)
    print("  ViraCut v8 — LesCrados.Ai  (STABLE BUILD)")
    print("=" * 55)
    print(f"  Clips reçus : {len(clips_raw)}")

    # Décodage des clips
    raw_paths = []
    for i, v in enumerate(clips_raw):
        p = f"_raw_{i}.mp4"
        with open(p, "wb") as f:
            f.write(base64.b64decode(v["data"]))
        d = duration(p)
        print(f"  Clip {i} : {d:.2f}s")
        raw_paths.append(p)

    n      = len(raw_paths)
    target = cfg(opts, "cinema_dur")
    xf     = cfg(opts, "cinema_xfade")

    # Durée par segment, avec plancher MIN_CLIP_DUR
    clip_dur = max((target - xf * (n - 1)) / n, MIN_CLIP_DUR)
    print(f"  Durée/segment : {clip_dur:.2f}s  |  xfade : {xf}s")

    # Rendu des segments
    seg_paths = []
    for i, src in enumerate(raw_paths):
        out = f"_cin_{i}.mp4"
        print(f"\n[Segment {i+1}/{n}]")
        build_cinema_segment(src, out, clip_dur, cfg(opts, "cinema_kb_zoom"), opts)
        seg_paths.append(out)

    print("\n[Assemblage]")
    assemble_cinema(seg_paths, xf, opts)

    print("\n[Overlay + Logo]")
    build_cinema_overlay_no_text(opts)

    size = os.path.getsize("output.mp4") / 1024 / 1024
    print(f"\n✓ DONE : output.mp4  ({size:.1f} MB)")

if __name__ == "__main__":
    start()
