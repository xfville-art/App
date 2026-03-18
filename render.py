"""
render.py — ViraCut Studio v12  ★ LesCrados.Ai Edition ★
═════════════════════════════════════════════════════════
v12 : SMART CUT ENGINE
     — motion_start : détection du 1er frame d'action réelle (skip intro statique)
     — punchline_seek : repérage du pic d'action dans le dernier clip
     — zoom progressif adaptatif : push-in hook + explosion zoom punch
     — grade BD renforcé : saturation/contraste Crados
v11 : CONCAT CUT ENGINE + Stickers IA BD style (v2)
v10 : VIRALITÉ ANALYSIS ENGINE
v9  : DIALOGUE CUT ENGINE
"""
import json, base64, os, subprocess, sys, re, urllib.request, urllib.error

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "mode":            "auto",
    "resolution":      "720x1280",
    "fps":             24,
    "crf":             18,
    "audio_br":        192,
    "fade_dur":        0.3,
    "cinema_dur":      12,
    "cinema_clip_min": 7,
    "cinema_clip_max": 12,
    "cinema_xfade":    0.2,
    "cinema_kb_zoom":  1.0,
    "cinema_lb_h":     80,

    # ── Dialogue Cut Engine ─────────────────────────────────────────
    "dialogue_cut":       False,
    "dialogue_noise_db":  -28,
    "dialogue_min_pause": 0.08,
    "dialogue_tolerance": 1.5,
    "dialogue_in_snap":   False,
    "dialogue_xfade_min": 0.15,
    "dialogue_xfade_max": 0.35,

    # ── Smart Cut Engine (v12) ──────────────────────────────────────
    "smart_cut":          True,   # ON — détecte intro statique + pic punchline
    "scene_thr":          0.06,   # seuil scenedetect (0.04=sensible, 0.10=strict)
    "static_max_skip":    2.0,    # skip intro statique jusqu'à 2s max
    "punch_zoom":         True,   # zoom-in progressif sur le clip punchline
    "hook_zoom":          True,   # léger push-in sur le clip hook
    "zoom_punch_scale":   1.10,   # zoom max sur la punchline (1.10 = +10%)
    "zoom_hook_scale":    1.05,   # zoom max sur le hook (1.05 = +5%)
    "grade_saturation":   1.18,   # saturation BD Crados
    "grade_contrast":     1.15,   # contraste BD Crados
    "grade_brightness":   -0.01,  # légère baisse luminosité
}

MIN_CLIP_DUR = 1.5

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
# DIALOGUE CUT ENGINE
# ═══════════════════════════════════════════════════════════════════════

def detect_silences(path, noise_db=-35, min_dur=0.10):
    """
    Detecte les intervalles de silence dans l audio d un clip.
    Retourne [(start, end), ...] trie par start.
    Retourne [] si pas d audio ou si FFmpeg echoue.
    """
    if not has_audio(path):
        return []
    cmd = (
        f'ffmpeg -i "{path}" '
        f'-af "silencedetect=noise={noise_db}dB:d={min_dur}" '
        f'-f null - 2>&1'
    )
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    output = r.stdout + r.stderr

    silences = []
    pending_start = None
    for line in output.splitlines():
        m = re.search(r'silence_start:\s*([\d.]+)', line)
        if m:
            pending_start = float(m.group(1))
        m = re.search(r'silence_end:\s*([\d.]+)', line)
        if m and pending_start is not None:
            silences.append((pending_start, float(m.group(1))))
            pending_start = None

    return sorted(silences, key=lambda x: x[0])


def find_cut_out(silences, target, clip_max, tolerance):
    """
    Trouve le meilleur point de coupe OUT.

    Priorite :
      1. Midpoint de la pause la plus proche de target (dans +/-tolerance)
      2. End-edge de la pause si mid depasse clip_max
      3. Start-edge de la pause
      4. target brut (fallback)

    Retourne (cut_time, label). cut_time est toujours <= clip_max.
    """
    window_lo = target - tolerance
    window_hi = target + tolerance

    # Construire les candidats : silences qui chevauchent la fenetre
    candidates = []
    for (s, e) in silences:
        if e < window_lo or s > window_hi:
            continue
        mid  = (s + e) / 2.0
        dist = abs(mid - target)
        candidates.append((dist, mid, s, e))
    candidates.sort(key=lambda x: x[0])

    for (dist, mid, s, e) in candidates:
        if mid <= clip_max:
            print(f"      snap OUT -> silence mid  {mid:.3f}s  "
                  f"[{s:.2f}-{e:.2f}]  delta={dist:.3f}s")
            return mid, "silence_mid"
        if e <= clip_max:
            print(f"      snap OUT -> silence end  {e:.3f}s  "
                  f"[{s:.2f}-{e:.2f}]")
            return e, "silence_end"
        if s >= 0.5:
            cut = min(s, clip_max)
            print(f"      snap OUT -> silence start {cut:.3f}s  "
                  f"[{s:.2f}-{e:.2f}]")
            return cut, "silence_start"

    cut = min(target, clip_max)
    print(f"      snap OUT -> fallback {cut:.3f}s  "
          f"(aucun silence dans +/-{tolerance}s)")
    return cut, "fallback"


def find_cut_in(silences, src_dur, min_in=0.20, tolerance=0.40):
    """
    Trouve le meilleur point d entree IN.
    Cherche la fin de la premiere pause dans [0, min_in+tolerance]
    pour demarrer proprement apres un silence d intro.
    Retourne (in_time, label).
    """
    window_hi = min_in + tolerance
    for (s, e) in silences:
        if s > window_hi:
            break
        candidate = min(e, window_hi)
        if candidate > 0.05:
            print(f"      snap IN  -> {candidate:.3f}s  "
                  f"(debut apres pause [{s:.2f}-{e:.2f}])")
            return candidate, "silence_end"

    print(f"      snap IN  -> 0.000s  (fallback)")
    return 0.0, "fallback"


def is_in_speech(silences, t, margin=0.12):
    """
    Retourne True si t est en plein discours
    (loin de toute pause de plus de margin s).
    """
    for (s, e) in silences:
        if (s - margin) <= t <= (e + margin):
            return False
    return True


def adaptive_xfade(out_silences, in_silences, cut_out_t, xf_base, xf_min, xf_max):
    """
    Calcule la duree de xfade optimale pour une transition.

    - discours -> discours  : coupe seche (xf_min) — TikTok-style
    - silence  -> silence   : fondu doux  (xf_max) — cinematique
    - mixte                 : xf_base
    """
    out_speech = is_in_speech(out_silences, cut_out_t, margin=0.12)
    in_speech  = (len(in_silences) == 0 or in_silences[0][0] > 0.20)

    if out_speech and in_speech:
        xf, lbl = xf_min, "cut sec (discours->discours)"
    elif not out_speech and not in_speech:
        xf, lbl = xf_max, "fondu long (pause->pause)"
    else:
        xf, lbl = xf_base, "xfade standard (mixte)"

    print(f"      xfade adaptatif : {xf:.2f}s  [{lbl}]")
    return xf


# ═══════════════════════════════════════════════════════════════════════
# LOGO SPLASH ANIME
# ═══════════════════════════════════════════════════════════════════════
def build_logo_splash(out, opts):
    """
    Outro Pixar-style — 2.5s cinématique.
    Filtres FFmpeg stables uniquement (pas de fontsize dynamique, pas de geq complexe).
    """
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps"); crf = cfg(opts, "crf")
    Wi, Hi = int(W), int(H)
    dur  = 2.5

    # Tailles basees sur Hi — CRADOS dominant
    margin    = int(Wi * 0.06)          # 6% marge chaque cote
    max_w     = Wi - margin * 2
    # Impact ~ 0.76 par caractere — coefficient calibre empiriquement
    crados_sz = int(max_w / (len("CRADOS") * 0.76))
    # (pas de min supplementaire — max_w/0.76 garantit deja le fit)
    les_sz    = int(crados_sz * 0.44)
    ai_sz     = int(crados_sz * 0.48)
    gap1      = int(crados_sz * 0.06)
    gap2      = int(crados_sz * 0.05)
    total_h   = les_sz + gap1 + crados_sz + gap2 + ai_sz
    block_top = (Hi - total_h) // 2
    les_y    = block_top
    crados_y = block_top + les_sz + gap1
    ai_y     = block_top + les_sz + gap1 + crados_sz + gap2

    # Fond : geq radial simple — halo rouge stable
    cx = Wi // 2; cy = Hi // 2
    hr = int(min(Wi, Hi) * 0.55)
    cx_str = str(Wi // 2); cy_str = str(Hi // 2); hr_str = str(int(min(Wi, Hi) * 0.55))
    bg_filter = (
        "geq="
        "r='clip(140*max(0,1-sqrt((X-"+cx_str+")*(X-"+cx_str+")+(Y-"+cy_str+")*(Y-"+cy_str+"))/"+hr_str+"),0,255)':"
        "g='clip(5*max(0,1-sqrt((X-"+cx_str+")*(X-"+cx_str+")+(Y-"+cy_str+")*(Y-"+cy_str+"))/"+hr_str+"),0,255)':"
        "b='clip(8*max(0,1-sqrt((X-"+cx_str+")*(X-"+cx_str+")+(Y-"+cy_str+")*(Y-"+cy_str+"))/"+hr_str+"),0,255)'"
    )

    # LES — fade in 0→0.3s
    dt_les = (
        f"drawtext=fontfile={FONT}:text='LES':fontsize={les_sz}:"
        f"fontcolor=white:x=(w-text_w)/2:y={les_y}:"
        f"alpha='if(lt(t,0.3),t/0.3,1)':enable='gte(t,0)'"
    )

    # CRADOS — fade in 0.2→0.5s
    dt_crad = (
        f"drawtext=fontfile={FONT}:text='CRADOS':fontsize={crados_sz}:"
        f"fontcolor=white:x=(w-text_w)/2:y={crados_y}:"
        f"alpha='if(lt(t,0.2),0,if(lt(t,0.5),(t-0.2)/0.3,1))':enable='gte(t,0.2)'"
    )

    # .Ai — fade in 0.5→0.8s, rouge
    dt_ai = (
        f"drawtext=fontfile={FONT}:text='.Ai':fontsize={ai_sz}:"
        f"fontcolor=#FF2442:x=(w-text_w)/2:y={ai_y}:"
        f"alpha='if(lt(t,0.5),0,if(lt(t,0.8),(t-0.5)/0.3,1))':enable='gte(t,0.5)'"
    )

    # Ligne rouge statique sous CRADOS
    line_h = max(3, int(crados_sz * 0.018))
    line_w = int(max_w * 0.90)
    line_x = (Wi - line_w) // 2
    line_y = crados_y + crados_sz + int(crados_sz * 0.025)
    dt_line = (
        f"drawbox=x={line_x}:y={line_y}:w={line_w}:h={line_h}:"
        f"color=#FF2442@0.9:t=fill:enable='gte(t,0.6)'"
    )

    # Scanlines : 1 ligne noire tous les 4px — look CRT/carte collector
    # step=4 pour limiter la longueur de la chaine de filtres (~16k chars)
    scanlines = []
    for _sy in range(0, Hi, 4):
        scanlines.append(
            "drawbox=x=0:y=" + str(_sy) + ":w=" + str(Wi) + ":h=1:color=black@0.22:t=fill"
        )

    # Vignette native FFmpeg
    vignette_f = "vignette=PI/3.5:eval=frame"

    vf_parts = [bg_filter, dt_les, dt_crad, dt_ai, dt_line] + scanlines + [
        vignette_f,
        "fade=t=in:st=0:d=0.2",
        f"fade=t=out:st={dur-0.4:.2f}:d=0.4",
    ]
    vf = ",".join(vf_parts)

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
        f'-c:v libx264 -pix_fmt yuv420p -crf {cfg(opts, "crf")} -c:a aac -ar 44100 -ac 2 output.mp4'
    )


# ═══════════════════════════════════════════════════════════════════════
# SEGMENTS CINEMA + DIALOGUE SNAP
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# SMART CUT ENGINE (v12) — détection intro statique + pic punchline
# ═══════════════════════════════════════════════════════════════════════

def detect_motion_start(path, scene_thr=0.06, max_skip=2.0):
    """
    Trouve le premier timestamp où l'action réelle commence.
    Skip l'intro statique typique des clips AI/Grok (carte affichée avant animation).
    Retourne (in_pt, label).
    """
    if not os.path.exists(path):
        return 0.0, "no_file"
    cmd = (
        f'ffmpeg -i "{path}" '
        f'-vf "select=gt(scene\\,{scene_thr}),showinfo" '
        f'-f null - 2>&1'
    )
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    output = r.stdout + r.stderr
    first_change = None
    for line in output.splitlines():
        if "pts_time:" in line and "showinfo" in line:
            try:
                t = float(line.split("pts_time:")[1].split()[0])
                if first_change is None:
                    first_change = t
                    break
            except Exception:
                pass
    if first_change is None:
        return 0.0, "no_change"
    if first_change < 0.08:
        return 0.0, "no_static_intro"
    in_pt = min(first_change, max_skip)
    src_dur = duration(path)
    if src_dur > 0 and in_pt > src_dur * 0.60:
        return 0.0, "skip_too_large"
    print(f"      motion_start : premier changement @{first_change:.3f}s → in_pt={in_pt:.3f}s")
    return in_pt, f"skip_static@{first_change:.2f}s"


def detect_punchline_peak(path, in_pt=0.0, scene_thr=0.05):
    """
    Repère le premier changement significatif dans la 2ème moitié du clip.
    Pour Les Crados : révélation (bouche ouverte, explosion) souvent en fin de clip.
    Retourne peak_t depuis in_pt, ou None.
    """
    if not os.path.exists(path):
        return None
    cmd = (
        f'ffmpeg -i "{path}" '
        f'-vf "select=gt(scene\\,{scene_thr}),showinfo" '
        f'-f null - 2>&1'
    )
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    output = r.stdout + r.stderr
    changes = []
    for line in output.splitlines():
        if "pts_time:" in line and "showinfo" in line:
            try:
                t = float(line.split("pts_time:")[1].split()[0])
                if t >= in_pt:
                    changes.append(t - in_pt)
            except Exception:
                pass
    if not changes:
        return None
    src_dur = duration(path)
    usable_dur = max(src_dur - in_pt, 1.0)
    mid = usable_dur * 0.45
    late_changes = [t for t in changes if t >= mid]
    if late_changes:
        peak = late_changes[0]
        print(f"      punchline_peak : @{peak:.3f}s (depuis in_pt={in_pt:.3f}s)")
        return peak
    return None


def build_cinema_segment(src, seg_out, target_dur, kb_zoom, opts, role="core"):
    """
    Extrait un segment depuis src avec :
      - Smart Cut IN  : skip intro statique via motion_start
      - Smart Cut OUT : étend si punchline pas encore incluse (role=punch)
      - Zoom progressif adaptatif selon le rôle (hook/core/punch)
      - Grade BD renforcé
    Retourne un dict avec les metadonnées du segment.
    """
    W, H    = cfg(opts, "resolution").split("x")
    fps     = cfg(opts, "fps")
    crf     = cfg(opts, "crf")
    src_dur = duration(src)

    use_smart   = cfg(opts, "smart_cut")
    scene_thr   = cfg(opts, "scene_thr")
    max_skip    = cfg(opts, "static_max_skip")
    do_pzoom    = cfg(opts, "punch_zoom")
    do_hzoom    = cfg(opts, "hook_zoom")
    zoom_punch  = cfg(opts, "zoom_punch_scale")
    zoom_hook   = cfg(opts, "zoom_hook_scale")
    sat         = cfg(opts, "grade_saturation")
    cont        = cfg(opts, "grade_contrast")
    bri         = cfg(opts, "grade_brightness")

    # ── Smart Cut IN : skip intro statique ───────────────────────────
    if use_smart:
        in_pt, in_lbl = detect_motion_start(src, scene_thr=scene_thr, max_skip=max_skip)
    else:
        in_pt, in_lbl = 0.0, "smart_off"

    clip_max = max(src_dur - in_pt, 1.0)

    # ── Smart Cut OUT : si role=punch, s'assurer d'inclure le pic ────
    if use_smart and role == "punch":
        peak = detect_punchline_peak(src, in_pt=in_pt, scene_thr=scene_thr * 0.85)
        if peak is not None:
            # On prend au minimum jusqu'au pic + 0.6s de résolution
            min_dur_for_peak = peak + 0.6
            actual = min(max(target_dur, min_dur_for_peak), clip_max)
            out_lbl = f"peak_included@{peak:.2f}s"
        else:
            actual = min(target_dur, clip_max)
            out_lbl = "no_peak"
    else:
        actual = min(target_dur, clip_max)
        out_lbl = "no_peak"

    actual = max(actual, 1.0)  # garde-fou absolu

    # ── Filtres video ────────────────────────────────────────────────
    # Grade BD renforcé — saturation/contraste Crados
    grade = f"eq=saturation={sat}:brightness={bri}:contrast={cont}"

    # Zoom progressif adaptatif selon le rôle
    # zoompan = lent (1 frame/output) — on utilise crop+scale pour la perf
    # push-in : zoom de 1.0 → zoom_max sur toute la durée du segment
    if role == "punch" and do_pzoom:
        # Zoom-in explosif sur la punchline
        zmax = zoom_punch
        # scale légèrement oversized puis crop centré progressif
        scale_w = int(int(W) * zmax)
        scale_h = int(int(H) * zmax)
        # Expression linéaire : crop_w va de scale_w*1.0 → int(W) sur nb_frames
        # On utilise zoompan natif FFmpeg — plus simple et stable
        zoom_filter = (
            f"zoompan=z='min(zoom+{(zmax-1.0)/int(fps/1.2):.6f},{zmax})'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}"
        )
        vf = f"fps={fps},{grade},{zoom_filter}"
    elif role == "hook" and do_hzoom:
        # Léger push-in sur le hook — plus subtil
        zmax = zoom_hook
        zoom_filter = (
            f"zoompan=z='min(zoom+{(zmax-1.0)/int(fps/1.5):.6f},{zmax})'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}"
        )
        vf = f"fps={fps},{grade},{zoom_filter}"
    else:
        # Core / pas de zoom : grade seul
        vf = f"fps={fps},{grade}"

    # ── Extraction ────────────────────────────────────────────────────
    ss_flag = f"-ss {in_pt:.3f}" if in_pt > 0.001 else ""

    if has_audio(src):
        run(
            f'ffmpeg -y {ss_flag} -t {actual:.3f} -i "{src}" '
            f'-vf "{vf}" -c:v libx264 -crf {crf} -c:a aac -shortest "{seg_out}"'
        )
    else:
        run(
            f'ffmpeg -y {ss_flag} -t {actual:.3f} -i "{src}" '
            f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
            f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{actual:.3f}[a]" '
            f'-map "[v]" -map "[a]" -c:v libx264 -crf {crf} "{seg_out}"'
        )

    print(f"      => in={in_pt:.3f}s  out={in_pt+actual:.3f}s  "
          f"dur={actual:.3f}s  [{in_lbl} / {out_lbl}]")

    return {
        "path":     seg_out,
        "in_pt":    in_pt,
        "out_pt":   in_pt + actual,
        "dur":      actual,
        "silences": [],
    }


def assemble_cinema(segments, opts):
    """
    Assemble les segments en cuts nets (pas de xfade).
    Le xfade ffmpeg entre clips H264 de sources hétérogènes génère
    des artefacts pixel (blocs colorés). Cut net = propre et pro.
    """
    seg_paths = [s["path"] for s in segments]

    if len(seg_paths) == 1:
        run(f'cp "{seg_paths[0]}" _assembled.mp4')
        return

    crf = cfg(opts, "crf")
    # Concat direct — clips déjà normalisés à la sanitisation
    with open("_concat.txt", "w") as f:
        for p in seg_paths:
            f.write(f"file '{p}'\n")
    run(
        f'ffmpeg -y -f concat -safe 0 -i _concat.txt '
        f'-c copy _assembled.mp4'
    )



def build_cinema_overlay_no_text(opts):
    W, H    = cfg(opts, "resolution").split("x")
    Wi, Hi  = int(W), int(H)
    lb_h    = cfg(opts, "cinema_lb_h")
    total   = duration("_assembled.mp4")
    fade_out_st = max(0.0, total - 0.6)
    fade_in_d   = 0.25  # fade-in vidéo propre au début

    lb = (
        f"drawbox=y=0:h={lb_h}:c=black@1:t=fill,"
        f"drawbox=y={Hi - lb_h}:h={lb_h}:c=black@1:t=fill"
    )
    # Vignette légère pour look cinématique
    vignette = "vignette=PI/4.5:eval=frame"
    # Fade in + fade out vidéo
    fades = f"fade=t=in:st=0:d={fade_in_d},fade=t=out:st={fade_out_st:.2f}:d=0.6"

    vf = f"{lb},{vignette},{fades}"

    # Audio : fade out calé sur la vraie durée (garde-fou min 0.5s de contenu)
    audio_fade_d = min(0.8, total * 0.15)
    audio_fade_st = max(0.0, total - audio_fade_d)

    run(
        f'ffmpeg -y -i _assembled.mp4 '
        f'-vf "{vf}" -af "afade=t=out:st={audio_fade_st:.2f}:d={audio_fade_d:.2f}" '
        f'-c:v libx264 -crf {cfg(opts,"crf")} _premain.mp4'
    )
    append_logo("_premain.mp4", opts)


# ═══════════════════════════════════════════════════════════════════════
# VIRALITÉ ANALYSIS ENGINE  (v10)
# ═══════════════════════════════════════════════════════════════════════
VIRALITE_MARKER_START = "##VIRALITE_JSON_START##"
VIRALITE_MARKER_END   = "##VIRALITE_JSON_END##"

def _call_github_models(api_key, prompt):
    """
    Appel GitHub Models (gratuit, toujours disponible dans GitHub Actions).
    Fallback séquentiel sur 4 modèles.
    """
    import re as _re
    models = [
        "meta-llama-3.3-70b-instruct",
        "gpt-4o-mini",
        "mistral-nemo",
        "meta-llama-3.1-8b-instruct",
    ]
    last_err = None
    for model in models:
        req = urllib.request.Request(
            "https://models.inference.ai.azure.com/chat/completions",
            data=json.dumps({
                "model":       model,
                "messages":    [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens":  1200,
            }).encode(),
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode())
            raw = body["choices"][0]["message"]["content"]
            print(f"      Modèle utilisé : {model}")
            return raw
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:200]
            print(f"      {model} → HTTP {e.code} — essai suivant")
            last_err = Exception(f"HTTP {e.code}: {err_body}")
        except Exception as e:
            print(f"      {model} → {e} — essai suivant")
            last_err = e
    raise last_err or Exception("Tous les modèles GitHub ont échoué")


def _extract_json(text):
    """Extrait le premier objet JSON valide depuis une réponse LLM."""
    import re as _re
    text = _re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=_re.MULTILINE)
    text = _re.sub(r'\s*```\s*$', '', text, flags=_re.MULTILINE).strip()
    start = text.find('{')
    if start == -1:
        raise ValueError("Aucun JSON trouvé dans la réponse")
    depth = 0
    for i, c in enumerate(text[start:], start):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("JSON incomplet dans la réponse")


def viralite_analysis(clips_raw, opts, raw_paths):
    """
    Analyse le potentiel viral TikTok des clips via GitHub Models.
    Aligne le prompt sur analyze.py (règles Les Crados, recommended_config).
    Écrit le résultat entre markers dans stdout pour parsing App.html.
    """
    api_key = os.environ.get("GITHUB_TOKEN", "")
    if not api_key:
        print("  [Viralité] GITHUB_TOKEN absent — analyse ignorée")
        return

    print("\n  [Viralité] Analyse en cours…")

    # Métadonnées clips (sans bytes vidéo — mesure durée réelle post-sanitisation)
    clips_meta = []
    for i, (v, path) in enumerate(zip(clips_raw, raw_paths)):
        try:
            dur   = duration(path)
            audio = has_audio(path)
        except Exception:
            dur, audio = 0, False
        clips_meta.append({
            "index":     i + 1,
            "role":      v.get("role", "auto"),
            "dur_s":     round(dur, 2),
            "has_audio": audio,
            "size_mb":   round(len(base64.b64decode(v["data"])) / 1_048_576, 2),
            "name":      v.get("name", f"clip_{i+1}.mp4"),
        })

    mode      = opts.get("mode", "auto")
    n_clips   = len(clips_meta)
    clips_desc = "\n".join(
        f"  Clip {c['index']} — rôle={c['role']} dur={c['dur_s']}s "
        f"audio={'oui' if c['has_audio'] else 'non'} "
        f"taille={c['size_mb']}MB nom={c['name']}"
        for c in clips_meta
    )

    # Durées réelles des sources pour guider le LLM
    src_dur_info = "\n".join(
        f"  Clip {c['index']} — {c['dur_s']}s dispo  (utilisation max recommandée)"
        for c in clips_meta
    )
    src_avg_dur = sum(c['dur_s'] for c in clips_meta) / len(clips_meta) if clips_meta else 6.0
    # Durées min/max suggérées basées sur la durée source
    hook_min = max(2.0, round(src_avg_dur * 0.30, 1))
    hook_max = round(src_avg_dur * 0.60, 1)
    punch_min = max(3.0, round(src_avg_dur * 0.45, 1))
    punch_max = round(src_avg_dur * 0.85, 1)

    prompt = f"""Tu es un expert TikTok spécialisé dans Les Crados (cartes satiriques absurdes style Garbage Pail Kids, public français, format 9:16).

Analyse ces clips et optimise la config pour maximiser la rétention TikTok.

CLIPS ({n_clips}) :
{clips_desc}

DURÉES SOURCES DISPONIBLES :
{src_dur_info}
⚠ IMPORTANT : hook_dur et punch_dur DOIVENT être dans les plages indiquées ci-dessous.
  Ne pas suggérer des durées plus courtes que les minimums — les clips AI ont besoin de temps pour s'exprimer.

CONFIG ACTUELLE :
- Mode : {mode.upper()}
- Hook dur : {opts.get('hook_dur', 2)}s
- Core dur : {opts.get('core_dur', 2.5)}s
- Punch dur : {opts.get('punch_dur', 3)}s
- Flash cut : {opts.get('flash_cut', True)}
- Zoom punch : {opts.get('zoom_punch', True)}
- Textes IA : {opts.get('ai_text', True)}
- Résolution : {opts.get('resolution', '720x1280')}

RÈGLES Les Crados TikTok :
- Durée idéale finale : 7-12s pour PUNCH (logo 2.5s inclus), 20-26s pour CINÉMA
- hook_dur : entre {hook_min}s et {hook_max}s (pas moins de {hook_min}s)
- punch_dur : entre {punch_min}s et {punch_max}s (pas moins de {punch_min}s)
- Le clip le plus visuellement fort = hook
- Punchline = dernier clip, doit être absurde/choquant
- Loop parfait = fin qui rappelle le début
- Flash cut + zoom punch = essentiels pour le PUNCH
- Si 1 seul clip : mode CINÉMA obligatoire

Réponds UNIQUEMENT en JSON valide, zéro texte avant ou après :
{{
  "score": <entier 0-100>,
  "axes": [
    {{"name": "Structure", "score": <0-100>}},
    {{"name": "Rythme",    "score": <0-100>}},
    {{"name": "Loop",      "score": <0-100>}},
    {{"name": "Diversité", "score": <0-100>}},
    {{"name": "Format",    "score": <0-100>}}
  ],
  "recs": [
    {{"type": "pos", "text": "<point fort concis max 60 chars>"}},
    {{"type": "neg", "text": "<point faible concis max 60 chars>"}},
    {{"type": "tip", "text": "<conseil actionnable max 60 chars>"}}
  ],
  "recommended_config": {{
    "mode": "<auto|punch|cinema>",
    "hook_dur": <float entre {hook_min} et {hook_max}>,
    "core_dur": <float>,
    "punch_dur": <float entre {punch_min} et {punch_max}>,
    "flash_cut": <bool>,
    "zoom_punch": <bool>,
    "ai_text": <bool>
  }}
}}"""

    try:
        raw_text = _call_github_models(api_key, prompt)
        result   = _extract_json(raw_text)
    except Exception as e:
        print(f"  [Viralité] Erreur API : {e}")
        return

    result["clips"] = n_clips
    result["mode"]  = mode

    # Affichage parseable par App.html
    print(f"  [Viralité] Score : {result['score']}/100")
    for ax in result.get("axes", []):
        print(f"    {ax['name']:12s}: {ax['score']}")
    rc = result.get("recommended_config", {})
    if rc:
        print(f"  [Viralité] Config recommandée → mode={rc.get('mode','?').upper()} "
              f"ordre={rc.get('clip_order','?')}")
    print(f"  {VIRALITE_MARKER_START}")
    print(json.dumps(result, ensure_ascii=False))
    print(f"  {VIRALITE_MARKER_END}")
    return result


# ═══════════════════════════════════════════════════════════════════════
# STICKER ENGINE  (v4) — Bulles BD calibrées
# Proportions correctes · Queue vers le personnage · Texte lisible
# ═══════════════════════════════════════════════════════════════════════
import math as _math


def _bd_stroke_text(draw, text, font, x, y, fill, stroke_col, sw=4, anchor="mm"):
    """Texte BD avec contour multi-directions."""
    for dx, dy in [(-sw,0),(sw,0),(0,-sw),(0,sw),
                   (-sw,-sw),(sw,-sw),(-sw,sw),(sw,sw)]:
        draw.text((x+dx, y+dy), text, fill=stroke_col, font=font, anchor=anchor)
    draw.text((x, y), text, fill=fill, font=font, anchor=anchor)


def _wrap_text(text, font, max_px):
    """Découpe le texte en lignes qui tiennent dans max_px."""
    words = text.upper().split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        try:    tw = font.getlength(test)
        except: tw = len(test) * 0.6 * font.size
        if tw > max_px and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def _gen_speech_bubble(text, bubble_w, out_path, tail_side="right", style="normal"):
    """
    Génère une bulle de dialogue BD.

    bubble_w  : largeur cible de la bulle en pixels (ex : 240)
                Le canvas PNG sera légèrement plus grand (queue + marges).

    tail_side : "right" → queue bas-droite (bulle à gauche du personnage)
                "left"  → queue bas-gauche (bulle à droite du personnage)

    style     : "normal" → blanc, texte noir   (réaction)
                "shout"  → jaune, texte rouge  (cri)
                "shock"  → orange dentelé      (choc)
                "thought"→ blanc nuage, bleu   (pensée)
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import random as _rnd
    except ImportError:
        return False

    FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

    # Palette par style
    if style == "shout":
        bg_col  = (255, 235, 20, 255)
        txt_col = (170, 0, 0, 255)
        sw_out  = max(5, bubble_w // 32)
    elif style == "shock":
        bg_col  = (255, 75, 20, 255)
        txt_col = (255, 255, 255, 255)
        sw_out  = max(5, bubble_w // 32)
    elif style == "thought":
        bg_col  = (235, 245, 255, 250)
        txt_col = (15, 15, 100, 255)
        sw_out  = max(4, bubble_w // 40)
    else:  # normal
        bg_col  = (255, 255, 255, 252)
        txt_col = (10, 10, 10, 255)
        sw_out  = max(5, bubble_w // 32)

    BLACK = (0, 0, 0, 255)

    # Dimensions bulle (ratio ~4:3 horizontal)
    bub_h  = int(bubble_w * 0.72)
    tail_h = int(bubble_w * 0.28)  # hauteur queue sous la bulle
    tail_w = int(bubble_w * 0.22)  # largeur base de la queue
    brad   = int(bubble_w * 0.22)  # rayon coins arrondis

    # Canvas : bulle + queue + marges pour le contour
    mg  = sw_out + 4
    W   = bubble_w + mg * 2
    H   = bub_h + tail_h + mg * 2

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Coordonnées bulle
    bx1 = mg
    by1 = mg
    bx2 = mg + bubble_w
    by2 = mg + bub_h
    bcx = (bx1 + bx2) // 2
    bcy = (by1 + by2) // 2

    # ── Corps de la bulle ─────────────────────────────────────────────
    if style == "shock":
        # Forme dentelée — étoile irrégulière
        _rnd.seed(hash(text) % 9999)
        n = 16
        ro = bubble_w // 2
        ri = int(ro * 0.76)
        pts = []
        for i in range(n * 2):
            ang = _math.radians(i * 180 / n - 90)
            r = ro if i % 2 == 0 else ri + _rnd.randint(-int(ri*0.06), int(ri*0.06))
            pts.append((bcx + r * _math.cos(ang), bcy + r * _math.sin(ang)))
        # Contour noir
        pts_s = [(bcx + (r + sw_out * 1.8) * _math.cos(_math.radians(i * 180/n - 90)),
                  bcy + (r + sw_out * 1.8) * _math.sin(_math.radians(i * 180/n - 90)))
                 for i, r in [(i, ro if i%2==0 else ri) for i in range(n * 2)]]
        d.polygon(pts_s, fill=BLACK)
        d.polygon(pts, fill=bg_col)

    elif style == "thought":
        # Ellipse principale + bosses régulières
        d.ellipse([bx1-sw_out, by1-sw_out, bx2+sw_out, by2+sw_out], fill=BLACK)
        d.ellipse([bx1, by1, bx2, by2], fill=bg_col)
        n_bumps = 12
        rx = bubble_w // 2
        ry = bub_h // 2
        bump_r = max(8, bubble_w // 18)
        for i in range(n_bumps):
            ang = _math.radians(i * 360 / n_bumps)
            bpx = int(bcx + rx * _math.cos(ang))
            bpy = int(bcy + ry * _math.sin(ang))
            d.ellipse([bpx-bump_r-sw_out, bpy-bump_r-sw_out,
                       bpx+bump_r+sw_out, bpy+bump_r+sw_out], fill=BLACK)
            d.ellipse([bpx-bump_r, bpy-bump_r,
                       bpx+bump_r, bpy+bump_r], fill=bg_col)
    else:
        # Bulle arrondie standard
        d.rounded_rectangle([bx1-sw_out, by1-sw_out, bx2+sw_out, by2+sw_out],
                             radius=brad + sw_out, fill=BLACK)
        d.rounded_rectangle([bx1, by1, bx2, by2], radius=brad, fill=bg_col)

    # ── Queue pointue ─────────────────────────────────────────────────
    if style not in ("shock", "thought"):
        # Base de la queue sur le bord bas de la bulle
        if tail_side == "right":
            q_cx = bx2 - int(bubble_w * 0.20)
            tip  = (bx2 + int(bubble_w * 0.04), by2 + tail_h + mg//2)
        else:  # left
            q_cx = bx1 + int(bubble_w * 0.20)
            tip  = (bx1 - int(bubble_w * 0.04), by2 + tail_h + mg//2)

        q_left  = q_cx - tail_w // 2
        q_right = q_cx + tail_w // 2
        tail_pts = [(q_left, by2), (q_right, by2), tip]

        # Contour noir queue
        d.polygon(tail_pts, fill=BLACK)
        # Corps queue (rentrant légèrement pour simuler l'épaisseur)
        sw2 = max(2, sw_out - 1)
        tail_in = [(q_left + sw2, by2 - sw2//2),
                   (q_right - sw2, by2 - sw2//2),
                   tip]
        d.polygon(tail_in, fill=bg_col)

    elif style == "thought":
        # Petites bulles qui descendent vers le personnage
        if tail_side == "right":
            centers = [(bx2 - int(bubble_w*0.10), by2 + int(tail_h*0.38)),
                       (bx2 + int(bubble_w*0.01),  by2 + int(tail_h*0.80))]
        else:
            centers = [(bx1 + int(bubble_w*0.10), by2 + int(tail_h*0.38)),
                       (bx1 - int(bubble_w*0.01),  by2 + int(tail_h*0.80))]
        radii = [max(6, bubble_w//14), max(4, bubble_w//22)]
        for (cx2, cy2), br in zip(centers, radii):
            d.ellipse([cx2-br-sw_out, cy2-br-sw_out, cx2+br+sw_out, cy2+br+sw_out], fill=BLACK)
            d.ellipse([cx2-br, cy2-br, cx2+br, cy2+br], fill=bg_col)

    # ── Texte ──────────────────────────────────────────────────────────
    # Police — taille de départ 28% de bubble_w, réduction si besoin
    usable_w = int(bubble_w * (0.70 if style == 'thought' else 0.80))
    usable_h = int(bub_h    * (0.68 if style == 'thought' else 0.76))
    # thought a moins d'espace utile (bosses) → police légèrement plus grande
    font_sz  = max(22, int(bubble_w * (0.30 if style == 'thought' else 0.28)))

    for _ in range(6):
        try:    fnt = ImageFont.truetype(FONT, font_sz)
        except: fnt = ImageFont.load_default(); break
        lines  = _wrap_text(text, fnt, usable_w)
        lh     = int(font_sz * 1.22)
        tot_h  = len(lines) * lh
        if tot_h <= usable_h:
            break
        font_sz = int(font_sz * 0.84)

    sw_txt = max(3, font_sz // 10)
    lh     = int(font_sz * 1.22)
    n_lines = len(lines)
    start_y = bcy - (n_lines - 1) * lh // 2

    for li, line in enumerate(lines):
        ly = start_y + li * lh
        _bd_stroke_text(d, line, fnt, bcx, ly, txt_col, BLACK, sw=sw_txt)

    img.save(out_path)
    return True


def _sticker_overlay_filter(stickers, video_w, video_h):
    """Filter FFmpeg pour overlay des bulles BD avec fade."""
    if not stickers:
        return [], "", 0

    input_args   = []
    filter_parts = []
    prev_label   = "0:v"
    nb_ok        = 0

    for idx, s in enumerate(stickers):
        img_path = f"_sticker_{idx}.png"

        text  = s.get("text",    "!")
        style = s.get("style",   "normal")
        tail  = s.get("tail",    "right")
        # bubble_w = largeur de la bulle en pixels (pas size du canvas)
        bw    = s.get("bubble_w", int(video_w * 0.34))
        x_pct = s.get("x_pct",  0.78)
        y_pct = s.get("y_pct",  0.18)
        t0    = float(s.get("t_start", 0.8))
        tdur  = float(s.get("t_dur",   2.0))

        ok = _gen_speech_bubble(text, bw, img_path, tail_side=tail, style=style)
        if not ok:
            continue

        # Taille réelle du PNG (bulle + queue + marges)
        try:
            from PIL import Image as _PI
            _im = _PI.open(img_path)
            png_w, png_h = _im.size
            _im.close()
        except Exception:
            png_w = int(bw * 1.15)
            png_h = int(bw * 1.05)

        # Position : coin de la vidéo, au-dessus du personnage
        # La queue pointe vers le bas → bulle au-dessus
        lb = 58   # hauteur letterbox
        px = int(video_w  * x_pct - png_w / 2)
        py = int(video_h  * y_pct - png_h / 2)
        # Clamp strict
        px = max(4,      min(px, video_w  - png_w - 4))
        py = max(lb + 4, min(py, video_h  - lb - png_h - 4))

        t_end   = t0 + tdur
        fade_in = min(0.12, tdur * 0.10)
        fade_out= min(0.15, tdur * 0.12)
        hold    = max(0.05, tdur - fade_in - fade_out)
        enable  = f"between(t,{t0:.3f},{t_end:.3f})"

        vf_stk = (
            f"[{idx+1}:v]"
            f"format=rgba,"
            f"loop=loop=-1:size=1,"
            f"trim=start=0:end={tdur:.3f},"
            f"fade=t=in:st=0:d={fade_in:.3f}:alpha=1,"
            f"fade=t=out:st={fade_in+hold:.3f}:d={fade_out:.3f}:alpha=1,"
            f"setpts=PTS+{t0:.3f}/TB"
            f"[s{idx}]"
        )
        ovl = (
            f"[{prev_label}][s{idx}]"
            f"overlay=x={px}:y={py}:format=auto:enable='{enable}'"
            f"[v{idx}]"
        )
        filter_parts.append(vf_stk)
        filter_parts.append(ovl)
        prev_label = f"v{idx}"
        input_args.extend(["-i", img_path])
        nb_ok += 1

    if not filter_parts:
        return [], "", 0

    last_label = f"[v{nb_ok-1}]"
    chain      = ";".join(filter_parts)
    last_idx   = chain.rfind(last_label)
    final_filter = (chain[:last_idx] + "[vout]" + chain[last_idx+len(last_label):]
                    if last_idx != -1 else chain)
    return input_args, final_filter, nb_ok


def sticker_analysis(segments, opts, vira_result):
    """
    Génère 2-3 bulles BD contextuelles via GitHub Models.
    Proportions calibrées : bubble_w_pct 0.30-0.40 de la largeur vidéo.
    """
    api_key = os.environ.get("GITHUB_TOKEN", "")

    if not opts.get("stickers", True):
        print("  [Stickers] Désactivés")
        return []

    W, H = cfg(opts, "resolution").split("x")
    W_px = int(W)
    H_px = int(H)

    content_dur = sum(s["dur"] for s in segments)

    # Description segments avec timecodes et rôle
    t_cur = 0.0
    segs_lines = []
    for i, s in enumerate(segments):
        role = "hook" if i == 0 else ("punch" if i == len(segments)-1 else "core")
        segs_lines.append(
            f"  Seg{i+1} [{role.upper()}]: "
            f"t={t_cur:.1f}s→{t_cur+s['dur']:.1f}s  dur={s['dur']:.1f}s"
        )
        t_cur += s["dur"]
    segs_desc = "\n".join(segs_lines)

    if not api_key:
        print("  [Stickers] Pas de token — défaut")
        return _default_stickers(W_px, content_dur, segments)

    prompt = (
        f"Tu es directeur artistique BD Les Crados (Garbage Pail Kids français, humour absurde/gore).\n"
        f"Vidéo TikTok 9:16 = {content_dur:.1f}s. Personnage grotesque sur carte collector animée.\n\n"
        f"SEGMENTS :\n{segs_desc}\n\n"
        f"Place exactement 2 bulles de dialogue BD. Règles STRICTES :\n\n"
        f"TEXTE : onomatopée ou réaction courte liée à l'ACTION du segment.\n"
        f"  hook   → l'action commence, personnage réagit. Ex: 'AÏÏE!', 'HÉ!', 'OUÏE!'\n"
        f"  core   → action en cours. Ex: 'AU SECOURS!', 'LÂCHEZ!', 'GNARK!'\n"
        f"  punch  → climax/révélation. Ex: 'BEURK!', 'NON!', 'ENCORE?!'\n"
        f"  MAX 8 CARACTÈRES ESPACES INCLUS. Tout en majuscules.\n\n"
        f"STYLE (choisir selon intensité) :\n"
        f"  normal  → blanc, réaction calme\n"
        f"  shout   → JAUNE, cri fort\n"
        f"  shock   → ORANGE dentelé, choc extrême\n"
        f"  thought → nuage blanc-bleu, pensée intérieure\n\n"
        f"PLACEMENT (TRÈS IMPORTANT — proportions réelles 720x1280px) :\n"
        f"  bubble_w_pct : 0.32 à 0.38 (largeur bulle / largeur vidéo)\n"
        f"    → 0.32 × 720 = 230px — lisible sans couvrir le visage\n"
        f"  x_pct : coin DROIT = 0.82 (tail='right') | coin GAUCHE = 0.18 (tail='left')\n"
        f"  y_pct : 0.14 à 0.28 — bulle flotte AU-DESSUS du personnage\n"
        f"  t_dur : 1.5 à 2.2s — durée courte, impact immédiat\n"
        f"  IMPORTANT : les 2 bulles NE DOIVENT PAS se chevaucher dans le temps\n\n"
        f"JSON UNIQUEMENT, rien d'autre :\n"
        f'{"{"}"stickers": [{{'
        f'"text":"<MAX 8 CHARS>",'
        f'"style":"<normal|shout|shock|thought>",'
        f'"tail":"<right|left>",'
        f'"bubble_w_pct":<float 0.32-0.38>,'
        f'"x_pct":<float>,'
        f'"y_pct":<float 0.14-0.28>,'
        f'"t_start":<float>,'
        f'"t_dur":<float 1.5-2.2>'
        f'}}]{"}"}'
    )

    print("  [Stickers] Appel LLM pour bulles BD…")
    try:
        raw  = _call_github_models(api_key, prompt)
        data = _extract_json(raw)
        raw_list = data.get("stickers", [])
        if not raw_list:
            raise ValueError("Liste vide")
    except Exception as e:
        print(f"  [Stickers] LLM erreur : {e} — défaut")
        return _default_stickers(W_px, content_dur, segments)

    stickers = []
    last_end = -99.0
    for s in raw_list[:3]:
        # Clamp bubble_w entre 28% et 42% de la vidéo
        bw_pct = float(s.get("bubble_w_pct", 0.34))
        bw_pct = max(0.28, min(bw_pct, 0.42))
        bw     = int(W_px * bw_pct)

        t0   = float(s.get("t_start", 0.5))
        tdur = float(s.get("t_dur",   1.8))
        # Pas de chevauchement : décaler si nécessaire
        if t0 < last_end + 0.3:
            t0 = last_end + 0.3
        t0   = max(0.2, min(t0, max(0.2, content_dur - 1.5)))
        tdur = max(1.0, min(tdur, content_dur - t0))
        last_end = t0 + tdur

        # Texte : truncate à 10 chars sécurité
        txt = str(s.get("text", "!")).upper()[:10].strip()
        if not txt:
            txt = "AÏÏE!"

        stickers.append({
            "text":     txt,
            "style":    s.get("style",  "normal"),
            "tail":     s.get("tail",   "right"),
            "bubble_w": bw,
            "x_pct":    float(s.get("x_pct",  0.82)),
            "y_pct":    float(s.get("y_pct",  0.18)),
            "t_start":  round(t0, 2),
            "t_dur":    round(tdur, 2),
        })
        print(f'    💬 "{txt}" [{stickers[-1]["style"]}] '
              f'bw={bw}px @{t0:.1f}s/{tdur:.1f}s '
              f'pos=({stickers[-1]["x_pct"]:.2f},{stickers[-1]["y_pct"]:.2f})')

    return stickers


def _default_stickers(W_px, content_dur, segments=None):
    """Bulles BD par défaut calibrées."""
    if content_dur < 1.5:
        return []
    bw = int(W_px * 0.34)
    n  = len(segments) if segments else 1
    out = [{"text": "AÏÏE!", "style": "shout",  "tail": "right",
             "bubble_w": bw, "x_pct": 0.82, "y_pct": 0.16,
             "t_start": min(0.4, content_dur * 0.08), "t_dur": 1.8}]
    if content_dur > 3.5 and n >= 2:
        out.append({"text": "BEURK!", "style": "shock", "tail": "left",
                    "bubble_w": bw, "x_pct": 0.18, "y_pct": 0.20,
                    "t_start": round(content_dur * 0.55, 1), "t_dur": 1.6})
    print(f"  [Stickers] {len(out)} bulle(s) par défaut")
    return out


def apply_stickers(input_video, output_video, stickers, opts):
    """Applique les bulles BD via FFmpeg overlay."""
    if not stickers:
        run(f'cp "{input_video}" "{output_video}"')
        return

    W_str, H_str = cfg(opts, "resolution").split("x")
    crf = cfg(opts, "crf")

    # Valider et corriger les timecodes
    try:
        vid_dur  = duration(input_video)
        stickers = [s for s in stickers if s.get("t_start", 0) < vid_dur - 0.5]
        for s in stickers:
            s["t_start"] = max(0.1, min(float(s["t_start"]), vid_dur - 1.0))
            s["t_dur"]   = max(0.5, min(float(s.get("t_dur", 1.8)), vid_dur - s["t_start"]))
        if not stickers:
            run(f'cp "{input_video}" "{output_video}"')
            return
    except Exception:
        pass

    input_args, filter_str, nb = _sticker_overlay_filter(
        stickers, int(W_str), int(H_str)
    )
    if not filter_str:
        run(f'cp "{input_video}" "{output_video}"')
        return

    cmd = (
        "ffmpeg -y"
        + f' -i "{input_video}"'
        + " " + " ".join(input_args)
        + f' -filter_complex "{filter_str}"'
        + f' -map "[vout]" -map "0:a:0"'
        + f' -c:v libx264 -crf {crf} -pix_fmt yuv420p -c:a aac -ar 44100'
        + f' "{output_video}"'
    )
    try:
        run(cmd)
        print(f"  [Stickers] {nb} bulle(s) BD appliquée(s) ✅")
    except Exception as e:
        print(f"  [Stickers] ERREUR : {e}")
        run(f'cp "{input_video}" "{output_video}"')



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

    print("=" * 60)
    print("  ViraCut v12 -- LesCrados.Ai  [SMART CUT ENGINE]")
    print("=" * 60)
    print(f"  Clips recus        : {len(clips_raw)}")
    print(f"  Smart Cut          : {cfg(opts,'smart_cut')}")
    print(f"  Scene threshold    : {cfg(opts,'scene_thr')}")
    print(f"  Static skip max    : {cfg(opts,'static_max_skip')}s")
    print(f"  Hook zoom          : {cfg(opts,'hook_zoom')} (×{cfg(opts,'zoom_hook_scale')})")
    print(f"  Punch zoom         : {cfg(opts,'punch_zoom')} (×{cfg(opts,'zoom_punch_scale')})")
    print(f"  Grade              : sat={cfg(opts,'grade_saturation')} cont={cfg(opts,'grade_contrast')}")

    # Decodage + sanitisation des clips sources
    # Force un re-encode propre pour éliminer les artefacts GOP des clips AI
    raw_paths = []
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps")
    crf  = cfg(opts, "crf")
    for i, v in enumerate(clips_raw):
        raw = f"_raw_{i}_orig.mp4"
        p   = f"_raw_{i}.mp4"
        with open(raw, "wb") as f:
            f.write(base64.b64decode(v["data"]))

        # Détecter les streams pour éviter le stream MJPEG parasite (ex: clips Grok)
        probe = ffprobe(raw)
        video_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
        audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]

        # Sélectionner le premier stream H264/HEVC — ignorer MJPEG thumbnail
        h264_idx = None
        for s in video_streams:
            if s.get("codec_name") in ("h264", "hevc", "vp9", "av1"):
                h264_idx = s.get("index")
                break
        if h264_idx is None and video_streams:
            h264_idx = video_streams[0].get("index")

        if len(video_streams) > 1:
            codecs = [s.get("codec_name") for s in video_streams]
            print(f"  Clip {i} : {len(video_streams)} streams vidéo {codecs} → stream #{h264_idx}")

        map_v = f"-map 0:{h264_idx}" if h264_idx is not None else "-map 0:v:0"

        # Re-encode : scale 9:16 + pad + GOP propre
        if audio_streams:
            run(
                f'ffmpeg -y -i "{raw}" {map_v} -map 0:a:0 '
                f'-vf "scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,'
                f'pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps}" '
                f'-c:v libx264 -crf {crf} -preset fast -pix_fmt yuv420p '
                f'-x264opts "keyint={fps}:no-scenecut" '
                f'-bf 0 -c:a aac -ar 44100 -ac 2 "{p}"'
            )
        else:
            # Source sans audio → générer silence
            run(
                f'ffmpeg -y -i "{raw}" -f lavfi -i "anullsrc=r=44100:cl=stereo" {map_v} -map 1:a '
                f'-vf "scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,'
                f'pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps}" '
                f'-c:v libx264 -crf {crf} -preset fast -pix_fmt yuv420p '
                f'-x264opts "keyint={fps}:no-scenecut" '
                f'-bf 0 -c:a aac -ar 44100 -ac 2 -shortest "{p}"'
            )

        d = duration(p)
        print(f"  Clip {i} : {d:.2f}s  audio={has_audio(p)}")
        raw_paths.append(p)

    # ── Ordre des clips ────────────────────────────────────────────
    # L'ordre est déjà appliqué côté app (clips[] réordonné par applyRecommendedConfig)
    # render.py traite toujours les clips dans l'ordre reçu — pas de réordonnancement ici
    print(f"  Ordre clips : séquentiel (ordre défini par l'app)")

    n        = len(raw_paths)
    # Durée initiale selon le mode UI (sera potentiellement affinée par la viralité)
    mode_eff = opts.get("mode", "auto").lower()
    if mode_eff == "punch":
        target = max(
            opts.get("hook_dur", 2.0) + opts.get("core_dur", 2.5) + opts.get("punch_dur", 3.0),
            n * 2.0   # plancher 2s/clip
        )
        target = min(target, 15)
    else:
        target = max(min(cfg(opts, "cinema_dur"), 60), n * 3.0)
    xf_b = 0.2
    clip_dur = max((target - xf_b * (n - 1)) / n, MIN_CLIP_DUR)
    print(f"\n  Mode effectif       : {mode_eff.upper()}")
    print(f"  Duree cible total   : {target:.2f}s")

    # ── Analyse viralité (avant rendu, après sanitisation) ─────────
    vira_result = viralite_analysis(clips_raw, opts, raw_paths)

    # ── Appliquer les recommandations viralité ─────────────────────
    if vira_result:
        rc = vira_result.get("recommended_config", {})

        # NB: clip_order ignoré — l'ordre est défini côté app dans clips[]

        # 1. Mode recommandé
        rec_mode = rc.get("mode", "").lower()
        if rec_mode in ("punch", "cinema", "auto") and rec_mode != mode_eff:
            print(f"  Mode viralité : {mode_eff.upper()} → {rec_mode.upper()}")
            opts["mode"] = rec_mode
            mode_eff = rec_mode

        # 2. Durées — le prompt impose déjà des plages min/max basées sur src_dur
        #    On applique avec planchers durs en dernier filet de sécurité
        src_avg = sum(duration(p) for p in raw_paths) / len(raw_paths)
        floor_hook  = max(2.0, round(src_avg * 0.30, 1))
        floor_punch = max(3.0, round(src_avg * 0.45, 1))
        if mode_eff == "punch":
            vhook  = max(float(rc.get("hook_dur",  opts.get("hook_dur",  2.0))), floor_hook)
            vpunch = max(float(rc.get("punch_dur", opts.get("punch_dur", 3.0))), floor_punch)
            vcore  = max(float(rc.get("core_dur",  opts.get("core_dur",  2.5))), 2.0)
            opts["hook_dur"]  = round(vhook,  2)
            opts["punch_dur"] = round(vpunch, 2)
            opts["core_dur"]  = round(vcore,  2)
            rec_total = vhook + vcore + vpunch
            target = min(max(rec_total, n * floor_hook), 15)
            clip_dur = max((target - xf_b * (n - 1)) / n, MIN_CLIP_DUR)
            print(f"  Durées viralité → hook={vhook:.1f}s core={vcore:.1f}s punch={vpunch:.1f}s  total={rec_total:.1f}s")
        else:
            target = min(max(opts.get("cinema_dur", cfg(opts, "cinema_dur")), n * 3.0), 60)
            clip_dur = max((target - xf_b * (n - 1)) / n, MIN_CLIP_DUR)
            print(f"  Durée segment (cinema/auto) : {clip_dur:.2f}s")

    # ── Durées par segment ──────────────────────────────────────────
    # Durées effectives = min(valeur UI/viralité, durée source dispo) mais plancher absolu
    src_durs = [duration(p) for p in raw_paths]
    src_avg  = sum(src_durs) / len(src_durs)

    mode_final = opts.get("mode", "auto").lower()
    if mode_final == "punch" and n == 1:
        # 1 seul clip en mode PUNCH → utiliser toute la source disponible
        # Les durées hook/punch n'ont pas de sens avec un seul clip
        seg_durs = [src_durs[0]]
        print(f"  Durées source   : {[round(d,2) for d in src_durs]}")
        print(f"  Durée/segment   : [{src_durs[0]:.2f}]  (1 clip — durée complète)")
    elif mode_final == "punch" and n >= 2:
        # Pour chaque segment : respecter la durée source (pas dépasser) avec plancher 2s/3s
        # Clip i → src_durs[i] disponible
        raw_hook  = float(opts.get("hook_dur",  2.0))
        raw_core  = float(opts.get("core_dur",  2.5))
        raw_punch = float(opts.get("punch_dur", 3.0))
        if n == 2:
            hook_d  = max(min(raw_hook,  src_durs[0]), 2.0)
            punch_d = max(min(raw_punch, src_durs[1]), 3.0)
            seg_durs = [hook_d, punch_d]
        elif n == 3:
            hook_d  = max(min(raw_hook,  src_durs[0]), 2.0)
            core_d  = max(min(raw_core,  src_durs[1]), 2.0)
            punch_d = max(min(raw_punch, src_durs[2]), 3.0)
            seg_durs = [hook_d, core_d, punch_d]
        else:
            seg_durs = []
            for k, sd in enumerate(src_durs):
                if k == 0:
                    seg_durs.append(max(min(raw_hook, sd), 2.0))
                elif k == len(src_durs) - 1:
                    seg_durs.append(max(min(raw_punch, sd), 3.0))
                else:
                    seg_durs.append(max(min(raw_core, sd), 2.0))
        print(f"  Durées source   : {[round(d,2) for d in src_durs]}")
        print(f"  Durées PUNCH    : {[round(d,2) for d in seg_durs]}")
    else:
        # CINEMA/AUTO : clip_dur déjà calculé, capper à la durée source
        seg_durs = [min(clip_dur, sd) for sd in src_durs]
        print(f"  Durées source   : {[round(d,2) for d in src_durs]}")
        print(f"  Durée/segment   : {[round(d,2) for d in seg_durs]}\n")


    # Rendu des segments
    segments = []
    for i, src in enumerate(raw_paths):
        out  = f"_cin_{i}.mp4"
        sdur = seg_durs[i]
        # Rôle basé sur la position : hook(0), punch(last), core(milieu)
        if n == 1:
            role = "punch"
        elif i == 0:
            role = "hook"
        elif i == n - 1:
            role = "punch"
        else:
            role = "core"
        print(f"{'─'*55}")
        print(f"  [Segment {i+1}/{n}  rôle={role.upper()}  cible={sdur:.2f}s]")
        seg = build_cinema_segment(src, out, sdur, 1.0, opts, role=role)
        segments.append(seg)

    print(f"\n{'─'*55}")
    print("  [Assemblage cuts nets — concat direct]")
    assemble_cinema(segments, opts)

    print("\n  [Overlay cinema + Logo splash]")
    build_cinema_overlay_no_text(opts)

    # ── Stickers intelligents ───────────────────────────────────────
    print("\n  [Stickers IA]")
    stickers = sticker_analysis(segments, opts, vira_result)
    if stickers:
        run('mv output.mp4 _presticker.mp4')
        apply_stickers("_presticker.mp4", "output.mp4", stickers, opts)
    else:
        print("  [Stickers] Aucun sticker appliqué")

    size = os.path.getsize("output.mp4") / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"  OK  output.mp4   {size:.1f} MB")
    print(f"{'='*60}")


if __name__ == "__main__":
    start()
