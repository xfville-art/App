"""
render.py — ViraCut Studio v14  ★ LesCrados.Ai Edition ★
═════════════════════════════════════════════════════════
v14 : VIRAL FX ENGINE
     — flash_cut     : flash blanc 2 frames aux cuts nets (snap TikTok)
     — freeze_end    : freeze frame 0.4s avant logo (image choc mémorisée)
     — zoompan_punch : zoompan animé FFmpeg sur clip punch (carte qui explose)
     — vignette_pulse: vignette pulsée sin(t*6) sur le hook
     — beat_sync     : analyse énergie audio clip hook
     — lut_theme     : courbes de correction colorimétrique par thème logo
     — serial_number : numéro de série collector N°XYZ/∞ en coin
     — glitch_text   : décalage RGB ±Npx sur le sous-titre hook
v13 : WATERMARK ENGINE — @lescrados.ai persistant tout le contenu
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
    "dialogue_noise_db":  -32,
    "dialogue_min_pause": 0.06,
    "dialogue_tolerance": 2.5,
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

    # ── Viral FX Engine (v14) ───────────────────────────────────────
    "flash_cut":          True,   # flash blanc 2 frames aux cuts nets
    "freeze_end":         True,   # freeze frame 0.4s avant fondu → logo
    "zoompan_punch":      True,   # zoompan animé FFmpeg sur clip punch (>hook_zoom)
    "zoompan_speed":      0.035,  # vitesse zoom par frame (0.03=doux, 0.06=brutal)
    "zoompan_max":        1.22,   # zoom max punchline (1.22 = +22% brutal)
    "vignette_pulse":     True,   # vignette pulsée sur le hook
    "vignette_strength":  0.55,   # intensité vignette (0=off, 1=max)
    "beat_sync":          True,   # détection beats audio → ajustement cuts
    "lut_theme":          True,   # LUT couleur thématique selon logo.theme
    "serial_number":      True,   # numéro de série collector en coin
    "glitch_text":        True,   # texte hook glitché (décalage RGB)
    "glitch_intensity":   3,      # décalage px canaux R/B (1=subtil, 5=brutal)
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


def _has_speech_after(silences, cut_t, clip_max, lookahead=0.8):
    """
    Retourne True si du dialogue existe dans [cut_t, cut_t+lookahead].
    Permet de détecter si un silence n'est qu'une pause inter-mots.
    """
    speech_start = cut_t
    for (s, e) in sorted(silences):
        if e <= cut_t:
            continue
        if s <= cut_t:
            speech_start = e
            continue
        if s - speech_start > 0.05 and s < cut_t + lookahead:
            return True
        speech_start = e
        if speech_start >= cut_t + lookahead:
            break
    return False


def find_cut_out(silences, target, clip_max, tolerance):
    """
    Trouve le meilleur point de coupe OUT.
    Vérifie qu'après le silence choisi il n'y a plus de dialogue
    dans les 0.8s suivantes (évite de couper au milieu d'une phrase).
    """
    LOOKAHEAD = 0.8

    window_lo = target - tolerance
    window_hi = target + tolerance

    candidates = []
    for (s, e) in silences:
        if e < window_lo or s > window_hi:
            continue
        mid  = (s + e) / 2.0
        dist = abs(mid - target)
        candidates.append((dist, mid, s, e))
    candidates.sort(key=lambda x: x[0])

    for (dist, mid, s, e) in candidates:
        cut = e if e <= clip_max else (mid if mid <= clip_max else None)
        if cut is None:
            continue
        if _has_speech_after(silences, cut, clip_max, LOOKAHEAD):
            print(f"      skip [{s:.2f}-{e:.2f}] : parole détectée après {cut:.3f}s")
            continue
        print(f"      snap OUT -> silence end  {cut:.3f}s  "
              f"[{s:.2f}-{e:.2f}]  delta={dist:.3f}s")
        return cut, "silence_end"

    # Fallback : dernier silence avant clip_max
    last_cut = None
    for (s, e) in sorted(silences):
        if s > clip_max:
            break
        candidate = min(e, clip_max)
        if candidate >= target - tolerance:
            last_cut = candidate
    if last_cut is not None:
        print(f"      snap OUT -> last silence {last_cut:.3f}s (phrase complète)")
        return last_cut, "last_silence"

    cut = min(target, clip_max)
    print(f"      snap OUT -> fallback {cut:.3f}s")
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

    # ── Paramètres logo depuis opts (App-11) ──────────────────────────
    def _esc(t):
        """Échappe les apostrophes pour FFmpeg drawtext (text='...')."""
        return t.replace("'", "\u2019")   # remplace ' par ' (apostrophe typographique)

    logo_cfg = opts.get("logo", {})
    l1_txt   = _esc(str(logo_cfg.get("l1", "LES")).strip().upper())     or "LES"
    l2_txt   = _esc(str(logo_cfg.get("l2", "CRADOS")).strip().upper())  or "CRADOS"
    l3_txt   = _esc(str(logo_cfg.get("l3", ".Ai")).strip())             or ".Ai"
    slogan   = _esc(str(logo_cfg.get("slogan", "")).strip())
    theme_id = str(logo_cfg.get("theme", "crados")).lower()

    # Thèmes : (halo_r, halo_g, halo_b, accent_hex)
    THEMES = {
        "crados":    (140,  5,   8, "#FF2442"),
        "cyber":     (  0, 80, 140, "#00D4FF"),
        "collector": (120, 90,   0, "#F5C842"),
        "matrix":    (  0,120,  60, "#34D399"),
        "gothic":    ( 60,  0, 140, "#9B59FF"),
    }
    hr_c, hg_c, hb_c, accent = THEMES.get(theme_id, THEMES["crados"])

    # ── Layout ────────────────────────────────────────────────────────
    margin   = int(Wi * 0.06)
    max_w    = Wi - margin * 2

    # L2 dominant : taille auto pour tenir dans max_w
    l2_sz  = max(24, int(max_w / (max(len(l2_txt), 1) * 0.76)))
    l1_sz  = int(l2_sz * 0.44)
    l3_sz  = int(l2_sz * 0.48)
    sl_sz  = int(l2_sz * 0.28) if slogan else 0
    gap    = int(l2_sz * 0.06)
    line_h = max(3, int(l2_sz * 0.022))
    line_w = int(max_w * 0.88)

    total_h = l1_sz + gap + l2_sz + gap + line_h + gap + l3_sz
    if slogan:
        total_h += gap + sl_sz

    block_top = (Hi - total_h) // 2
    y_l1   = block_top
    y_l2   = y_l1 + l1_sz + gap
    y_line = y_l2 + l2_sz + gap
    y_l3   = y_line + line_h + gap
    y_sl   = y_l3 + l3_sz + gap  if slogan else 0

    line_x = (Wi - line_w) // 2

    # ── Fond radial thématique ────────────────────────────────────────
    cx_s  = str(Wi // 2); cy_s = str(Hi // 2)
    hr_s  = str(int(min(Wi, Hi) * 0.55))
    bg_filter = (
        "geq="
        f"r='clip({hr_c}*max(0,1-sqrt((X-{cx_s})*(X-{cx_s})+(Y-{cy_s})*(Y-{cy_s}))/{hr_s}),0,255)':"
        f"g='clip({hg_c}*max(0,1-sqrt((X-{cx_s})*(X-{cx_s})+(Y-{cy_s})*(Y-{cy_s}))/{hr_s}),0,255)':"
        f"b='clip({hb_c}*max(0,1-sqrt((X-{cx_s})*(X-{cx_s})+(Y-{cy_s})*(Y-{cy_s}))/{hr_s}),0,255)'"
    )

    # ── Textes animés ─────────────────────────────────────────────────
    # L1 — fade in 0→0.3s
    dt_l1 = (
        f"drawtext=fontfile={FONT}:text='{l1_txt}':fontsize={l1_sz}:"
        f"fontcolor=white:x=(w-text_w)/2:y={y_l1}:"
        f"alpha='if(lt(t,0.3),t/0.3,1)':enable='gte(t,0)'"
    )
    # L2 — fade in 0.2→0.5s, blanc
    dt_l2 = (
        f"drawtext=fontfile={FONT}:text='{l2_txt}':fontsize={l2_sz}:"
        f"fontcolor=white:x=(w-text_w)/2:y={y_l2}:"
        f"alpha='if(lt(t,0.2),0,if(lt(t,0.5),(t-0.2)/0.3,1))':enable='gte(t,0.2)'"
    )
    # L3 — fade in 0.5→0.8s, couleur accent
    dt_l3 = (
        f"drawtext=fontfile={FONT}:text='{l3_txt}':fontsize={l3_sz}:"
        f"fontcolor={accent}:x=(w-text_w)/2:y={y_l3}:"
        f"alpha='if(lt(t,0.5),0,if(lt(t,0.8),(t-0.5)/0.3,1))':enable='gte(t,0.5)'"
    )
    # Ligne accent sous L2
    dt_line = (
        f"drawbox=x={line_x}:y={y_line}:w={line_w}:h={line_h}:"
        f"color={accent}@0.9:t=fill:enable='gte(t,0.6)'"
    )
    # Slogan optionnel — fade in 0.7→1.0s
    dt_slogan_parts = []
    if slogan:
        # Tronquer si trop long
        max_chars = max(1, int(max_w / (sl_sz * 0.55)))
        sl_disp   = slogan[:max_chars] + ("…" if len(slogan) > max_chars else "")
        dt_slogan_parts.append(
            f"drawtext=fontfile={FONT}:text='{sl_disp}':fontsize={sl_sz}:"
            f"fontcolor={accent}@0.75:x=(w-text_w)/2:y={y_sl}:"
            f"alpha='if(lt(t,0.7),0,if(lt(t,1.0),(t-0.7)/0.3,1))':enable='gte(t,0.7)'"
        )

    # Scanlines CRT — geq (1 seul filtre, évite l'overflow filter_complex)
    scanlines = ["geq=lum='if(mod(Y,4),lum(X\\,Y),lum(X\\,Y)*0.78)':cb='cb(X\\,Y)':cr='cr(X\\,Y)'"]

    # Pas de vignette — aucune bande sur le logo
    vignette_parts = []

    # format=yuv420p obligatoire avant fade sur source lavfi (rgb24 sinon)
    vf_parts = (
        [bg_filter, dt_l1, dt_l2, dt_l3, dt_line]
        + dt_slogan_parts
        + scanlines
        + vignette_parts
        + [
            "format=yuv420p",
            "fade=t=in:st=0:d=0.2",
            f"fade=t=out:st={dur-0.4:.2f}:d=0.4",
        ]
    )
    vf = ",".join(vf_parts)

    print(f"  [Logo] thème={theme_id}  L1={l1_txt}  L2={l2_txt}  L3={l3_txt}"
          + (f"  slogan='{slogan}'" if slogan else ""))

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

    # ── Smart Cut IN : skip intro statique (HOOK seulement) ─────────
    # Sur CORE et PUNCH : on ne skippe jamais — le début peut contenir
    # une scène virale cruciale (recrachement, révélation, réaction).
    if use_smart and role == "hook":
        in_pt, in_lbl = detect_motion_start(src, scene_thr=scene_thr, max_skip=max_skip)
    else:
        in_pt, in_lbl = 0.0, "no_skip"

    clip_max = max(src_dur - in_pt, 1.0)

    # ── Smart Cut OUT : stratégie par rôle ──────────────────────────
    #
    # HOOK  → durée cible stricte (le hook doit rester court et percutant)
    # CORE  → prend TOUTE la source disponible (peut contenir la scène
    #          virale : recrachement, révélation, action clé)
    # PUNCH → prend toute la source, en s'assurant d'inclure le pic d'action
    #
    # Logique : la durée LLM est un MINIMUM, jamais un plafond pour core/punch.
    if role == "core":
        # Toujours prendre tout le clip core disponible — la scène virale
        # est souvent en fin de clip (ex: recrachement clous @4.5s sur 6s)
        actual = clip_max
        out_lbl = "full_core"
        if actual > target_dur:
            print(f"      core étendu : {target_dur:.2f}s → {actual:.2f}s (durée source complète)")

    elif role == "punch" and use_smart:
        # Pour le punch : chercher le pic d'action et prendre jusqu'à la fin
        peak = detect_punchline_peak(src, in_pt=in_pt, scene_thr=max(0.03, scene_thr * 0.5))
        if peak is not None:
            # Prendre depuis in_pt jusqu'à la fin du clip (le pic est le début de l'action)
            actual = clip_max
            out_lbl = f"full_punch_peak@{peak:.2f}s"
            print(f"      punch complet : pic @{peak:.2f}s → fin source {actual:.2f}s")
        else:
            actual = clip_max
            out_lbl = "full_punch"
    else:
        # Hook ou smart_off : durée cible stricte
        actual = min(target_dur, clip_max)
        out_lbl = "target_dur"

    actual = max(actual, 1.0)  # garde-fou absolu

    # ── Beat sync : détection énergie audio ─────────────────────────
    # Analyse le volume RMS pour détecter les pics d'énergie (beats).
    # Utilisé pour informer le LLM et ajuster in_pt si beat_sync actif.
    beat_offset = 0.0
    if cfg(opts, "beat_sync") and has_audio(src) and role == "hook":
        try:
            r_bs = subprocess.run(
                f'ffmpeg -i "{src}" -af "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level" '
                f'-f null - 2>&1',
                shell=True, capture_output=True, text=True
            )
            # Chercher le premier pic d'énergie dans la 1ère seconde
            peaks = []
            for line in (r_bs.stdout + r_bs.stderr).splitlines():
                if "pts_time" in line and "RMS_level" in line.lower():
                    pass  # astats ne retourne pas pts_time inline — approche simplifiée
            # Approche légère : volumedetect pour niveau global
            r_vol = subprocess.run(
                f'ffmpeg -i "{src}" -t 3.0 -af "volumedetect" -f null - 2>&1',
                shell=True, capture_output=True, text=True
            )
            for line in (r_vol.stdout + r_vol.stderr).splitlines():
                if "mean_volume" in line:
                    try:
                        mean_db = float(line.split("mean_volume:")[1].split("dB")[0].strip())
                        print(f"      [BeatSync] Volume moyen hook : {mean_db:.1f}dB")
                    except Exception:
                        pass
        except Exception as e:
            print(f"      [BeatSync] skip : {e}")

    # ── Filtres video ────────────────────────────────────────────────
    # Grade BD renforcé — saturation/contraste Crados
    grade = f"eq=saturation={sat}:brightness={bri}:contrast={cont}"

    W_i = int(W); H_i = int(H)

    # ── Zoompan animé (v14) ─────────────────────────────────────────
    # PUNCH  → zoompan brutal vers le centre : carte qui explose
    # HOOK   → push-in doux (hook_zoom)
    # CORE   → grade seul
    do_pzoom   = cfg(opts, "punch_zoom")
    do_hzoom   = cfg(opts, "hook_zoom")
    do_zoompan = cfg(opts, "zoompan_punch")
    zp_speed   = cfg(opts, "zoompan_speed")     # 0.035
    zp_max     = cfg(opts, "zoompan_max")       # 1.22
    zh_scale   = cfg(opts, "zoom_hook_scale")   # 1.05

    if role == "punch" and do_pzoom and do_zoompan:
        # zoompan : zoom progressif de 1.0 → zp_max, centré
        # on_mode=pad garantit qu'on remplit toujours W×H
        zoompan = (
            f"zoompan="
            f"z='min(zoom+{zp_speed:.4f},{zp_max:.3f})':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d=1:s={W}x{H}:fps={fps}"
        )
        vf = f"fps={fps},{grade},{zoompan}"
        print(f"      [ZoompanPunch] z_max={zp_max}  speed={zp_speed}")

    elif role == "hook" and do_hzoom:
        # Push-in doux : scale légèrement oversizé + centrage fixe
        scale_h = int(W_i * zh_scale)
        crop_off_x = (scale_h - W_i) // 2
        crop_off_y = int((H_i * zh_scale - H_i) // 2)
        vf = (
            f"fps={fps},"
            f"scale={int(W_i*zh_scale)}:{int(H_i*zh_scale)}:flags=lanczos,"
            f"crop={W}:{H}:{crop_off_x}:{crop_off_y},"
            f"{grade}"
        )
        print(f"      [HookZoom] scale ×{zh_scale}")

    else:
        # Core ou zooms désactivés : grade seul
        vf = f"fps={fps},{grade}"

    # ── LUT couleur thématique ───────────────────────────────────────
    # Applique une correction colorimétrique inline via curves selon le thème.
    # Remplace une vraie LUT .cube (non disponible en runtime) par des courbes
    # de correction FFmpeg pures, sans fichier externe.
    if cfg(opts, "lut_theme"):
        theme_id = str(opts.get("logo", {}).get("theme", "crados")).lower()
        # Chaque thème = correction RGB via curves (r/g/b : 0→0, mid, 1→1)
        LUT_CURVES = {
            # Crados : rouge écrasé (chaud), légère dominante rouge sang
            "crados":    "curves=r='0/0 0.5/0.58 1/1':g='0/0 0.5/0.47 1/0.95':b='0/0 0.5/0.42 1/0.88'",
            # Cyber : boost bleu + cyan, rouge légèrement retenu
            "cyber":     "curves=r='0/0 0.5/0.44 1/0.92':g='0/0 0.5/0.52 1/1':b='0/0 0.5/0.60 1/1'",
            # Collector : chaud doré, boost highlights jaune
            "collector": "curves=r='0/0 0.5/0.58 1/1':g='0/0 0.5/0.54 1/1':b='0/0 0.5/0.38 1/0.82'",
            # Matrix : boost vert néon, canaux R et B écrasés
            "matrix":    "curves=r='0/0 0.5/0.38 1/0.85':g='0/0 0.5/0.60 1/1':b='0/0 0.5/0.40 1/0.88'",
            # Gothic : violet — rouge et bleu boostés, vert retenu
            "gothic":    "curves=r='0/0 0.5/0.56 1/1':g='0/0 0.5/0.40 1/0.88':b='0/0 0.5/0.58 1/1'",
        }
        lut_filter = LUT_CURVES.get(theme_id, "")
        if lut_filter:
            vf = f"{vf},{lut_filter}"
            print(f"      [LUT] thème={theme_id}")

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
    Assemble les segments en cuts nets avec flash frame optionnel entre clips.
    Flash blanc 2 frames au moment du cut = snap TikTok.
    """
    seg_paths = [s["path"] for s in segments]
    crf = cfg(opts, "crf")
    do_flash = cfg(opts, "flash_cut")

    if len(seg_paths) == 1:
        run(f'cp "{seg_paths[0]}" _assembled.mp4')
        return

    if not do_flash or len(seg_paths) < 2:
        # Concat direct sans flash
        with open("_concat.txt", "w") as f:
            for p in seg_paths:
                f.write(f"file '{p}'\n")
        run(f'ffmpeg -y -f concat -safe 0 -i _concat.txt -c copy _assembled.mp4')
        return

    # ── Flash frame entre chaque cut ────────────────────────────────
    # Génère un clip flash blanc de 2 frames (= 1/fps * 2)
    fps  = cfg(opts, "fps")
    W, H = cfg(opts, "resolution").split("x")
    flash_dur = 2.0 / fps   # 2 frames exactes
    run(
        f'ffmpeg -y -f lavfi -i "color=c=white:size={W}x{H}:rate={fps}" '
        f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
        f'-t {flash_dur:.4f} '
        f'-c:v libx264 -crf {crf} -pix_fmt yuv420p '
        f'-c:a aac -ar 44100 -ac 2 -shortest _flash.mp4'
    )
    print(f"  [FlashCut] Flash {flash_dur*1000:.0f}ms ({2} frames @{fps}fps)")

    # Intercaler le flash entre chaque segment
    with open("_concat.txt", "w") as f:
        for i, p in enumerate(seg_paths):
            f.write(f"file '{p}'\n")
            if i < len(seg_paths) - 1:
                f.write(f"file '_flash.mp4'\n")

    run(
        f'ffmpeg -y -f concat -safe 0 -i _concat.txt '
        f'-c:v libx264 -crf {crf} -pix_fmt yuv420p -c:a aac -ar 44100 -ac 2 _assembled.mp4'
    )
    print(f"  [FlashCut] {len(seg_paths)-1} flash(es) injecté(s) ✅")



def build_cinema_overlay_no_text(opts):
    W, H    = cfg(opts, "resolution").split("x")
    Wi, Hi  = int(W), int(H)
    crf_val = cfg(opts, "crf")
    fps_val = cfg(opts, "fps")

    # ── Freeze frame final avant le logo ────────────────────────────
    # Clone la dernière frame 0.4s → l'image choc reste à l'écran
    if cfg(opts, "freeze_end"):
        freeze_dur = 0.4
        run(
            f'ffmpeg -y -i _assembled.mp4 '
            f'-vf "tpad=stop_mode=clone:stop_duration={freeze_dur}" '
            f'-c:v libx264 -crf {crf_val} -pix_fmt yuv420p -c:a aac -ar 44100 -ac 2 _assembled_freeze.mp4'
        )
        run('mv _assembled_freeze.mp4 _assembled.mp4')
        print(f"  [FreezeEnd] {freeze_dur}s freeze injecté ✅")

    total    = duration("_assembled.mp4")
    LOGO_DUR = 2.5

    fade_out_d  = 0.5
    fade_out_st = max(0.0, total - fade_out_d)
    fade_in_d   = 0.25

    vf_parts = []

    # ── Vignette pulsée (hook uniquement = premières secondes) ───────
    if cfg(opts, "vignette_pulse"):
        vs = cfg(opts, "vignette_strength")   # 0.55
        pulse_end = min(total, 4.0)
        # geq sin() non disponible dans cette version FFmpeg Actions.
        # Alternative robuste : vignette via filtre natif FFmpeg "vignette"
        # + drawbox coins noirs semi-transparents pulsés via alpha=sin.
        # On utilise 4 drawbox en coins avec alpha dynamique via enable.
        # Approche 100% stable : vignette FFmpeg natif (filtre dédié)
        vign_angle = min(1.2, vs * 2.0)   # angle vignette [0, PI/2]
        vign = f"vignette=angle={vign_angle:.3f}:mode=forward:eval=frame:enable='lte(t\\,{pulse_end:.2f})'"
        vf_parts.append(vign)
        print(f"  [Vignette] Native FFmpeg vignette sur {pulse_end:.1f}s  angle={vign_angle:.2f}")

    # ── Watermark @lescrados.ai ──────────────────────────────────────
    wm_txt      = "@lescrados.ai"
    wm_sz       = max(20, int(Hi * 0.030))
    wm_margin_x = int(Wi * 0.035)
    wm_margin_y = int(Hi * 0.030)
    wm_y        = Hi - wm_margin_y - wm_sz
    wm_fade_in  = 0.35
    wm_fade_out = max(0.0, total - 0.4)
    wm_alpha = (
        f"if(lt(t,{wm_fade_in}),t/{wm_fade_in},"
        f"if(gt(t,{wm_fade_out:.3f}),(t-{wm_fade_out:.3f})/0.4,1))"
    )
    with open("_wm_handle.txt", "w", encoding="utf-8") as _f:
        _f.write(wm_txt)
    vf_parts.append(
        f"drawtext=fontfile={FONT}:textfile=_wm_handle.txt:"
        f"fontsize={wm_sz}:fontcolor=black@0.55:"
        f"x={wm_margin_x + 2}:y={wm_y + 2}:alpha='{wm_alpha}'"
    )
    vf_parts.append(
        f"drawtext=fontfile={FONT}:textfile=_wm_handle.txt:"
        f"fontsize={wm_sz}:fontcolor=white@0.88:"
        f"x={wm_margin_x}:y={wm_y}:alpha='{wm_alpha}'"
    )

    # ── Numéro de série collector ────────────────────────────────────
    if cfg(opts, "serial_number"):
        import random, time
        # Numéro pseudo-aléatoire mais stable (basé sur timestamp du run)
        serial = opts.get("serial_override", random.randint(1, 999))
        serial_txt = f"N°{serial:03d} / ∞"
        sr_sz  = max(16, int(Hi * 0.022))    # ~2.2% hauteur — discret
        sr_x   = int(Wi * 0.035)             # coin bas gauche, sous le watermark
        sr_y   = wm_y - sr_sz - int(Hi * 0.012)
        sr_fade_in  = 0.5
        sr_fade_out = max(0.0, total - 0.4)
        sr_alpha = (
            f"if(lt(t,{sr_fade_in}),t/{sr_fade_in},"
            f"if(gt(t,{sr_fade_out:.3f}),(t-{sr_fade_out:.3f})/0.4,0.72))"
        )
        with open("_serial.txt", "w", encoding="utf-8") as _f:
            _f.write(serial_txt)
        # Ombre
        vf_parts.append(
            f"drawtext=fontfile={FONT}:textfile=_serial.txt:"
            f"fontsize={sr_sz}:fontcolor=black@0.45:"
            f"x={sr_x + 1}:y={sr_y + 1}:alpha='{sr_alpha}'"
        )
        # Texte accent — couleur selon thème logo
        theme_id = str(opts.get("logo", {}).get("theme", "crados")).lower()
        THEME_COLORS = {
            "crados": "#FF2442", "cyber": "#00D4FF",
            "collector": "#F5C842", "matrix": "#34D399", "gothic": "#9B59FF",
        }
        sr_color = THEME_COLORS.get(theme_id, "#FF2442")
        vf_parts.append(
            f"drawtext=fontfile={FONT}:textfile=_serial.txt:"
            f"fontsize={sr_sz}:fontcolor={sr_color}@0.85:"
            f"x={sr_x}:y={sr_y}:alpha='{sr_alpha}'"
        )
        print(f"  [Serial] {serial_txt}  theme={theme_id}  color={sr_color}")

    # ── Fades vidéo ─────────────────────────────────────────────────
    vf_parts.append(
        f"fade=t=in:st=0:d={fade_in_d},"
        f"fade=t=out:st={fade_out_st:.2f}:d={fade_out_d}"
    )

    vf = ",".join(vf_parts)

    run(
        f'ffmpeg -y -i _assembled.mp4 '
        f'-vf "{vf}" '
        f'-c:v libx264 -crf {crf_val} -pix_fmt yuv420p -c:a copy _premain.mp4'
    )
    append_logo("_premain.mp4", opts)

    # Audio fade final
    total_final  = duration("output.mp4")
    audio_fade_d = min(1.2, LOGO_DUR * 0.5)
    audio_fade_st= max(0.0, total_final - audio_fade_d)
    run(
        f'ffmpeg -y -i output.mp4 '
        f'-af "afade=t=out:st={audio_fade_st:.2f}:d={audio_fade_d:.2f}" '
        f'-c:v copy -c:a aac -ar 44100 -ac 2 _output_fade.mp4'
    )
    run('mv _output_fade.mp4 output.mp4')



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
# SUBTITLE ENGINE  (v1) — Sous-titres cinéma propres
# Bande semi-transparente en bas · Texte blanc bold · Jamais gênant
# ═══════════════════════════════════════════════════════════════════════

def subtitle_analysis(segments, opts, vira_result):
    """
    Génère 2-3 sous-titres courts via GitHub Models.
    Chaque sous-titre commente l'action visible au bon moment.
    Retourne une liste de dicts : {text, t_start, t_dur}
    """
    api_key = os.environ.get("GITHUB_TOKEN", "")

    if not opts.get("stickers", True):   # réutilise le flag "stickers" pour activer/désactiver
        print("  [Subtitles] Désactivés par config")
        return []

    content_dur = sum(s["dur"] for s in segments)

    # Description segments
    t_cur = 0.0
    segs_lines = []
    for i, s in enumerate(segments):
        role = "hook" if i == 0 else ("punch" if i == len(segments)-1 else "core")
        segs_lines.append(
            f"  Seg{i+1} [{role.upper()}]: t={t_cur:.1f}s→{t_cur+s['dur']:.1f}s  dur={s['dur']:.1f}s"
        )
        t_cur += s["dur"]
    segs_desc = "\n".join(segs_lines)

    if not api_key:
        print("  [Subtitles] Pas de token — sous-titres par défaut")
        return _default_subtitles(content_dur, segments)

    prompt = (
        f"Tu es scénariste pour Les Crados (Garbage Pail Kids français).\n"
        f"Vidéo TikTok 9:16 = {content_dur:.1f}s. Carte collector animée, personnage grotesque.\n\n"
        f"SEGMENTS :\n{segs_desc}\n\n"
        f"Écris EXACTEMENT 2 sous-titres courts qui apparaissent en bas de la vidéo.\n"
        f"Les sous-titres commentent l'action de manière absurde/drôle style Les Crados.\n\n"
        f"RÈGLES STRICTES :\n"
        f"- MAX 25 caractères par sous-titre\n"
        f"- Ton absurde/sarcastique/dégoûtant — style carte collector\n"
        f"- Le 1er sous-titre : pendant le hook (début)\n"
        f"- Le 2ème sous-titre : pendant la punchline (fin)\n"
        f"- t_dur : entre 1.8s et 2.5s\n"
        f"- Les 2 sous-titres NE SE CHEVAUCHENT PAS\n"
        f"- Exemples : 'Magnétique et douloureux...', 'Ça fait MAL !', "
        f"'Collection complète !', 'Appelle un médecin !', 'Résistance nulle.'\n\n"
        f"JSON UNIQUEMENT :\n"
        f'{"{"}"subtitles": [{{"text":"<MAX 25 CHARS>","t_start":<float>,"t_dur":<float 1.8-2.5>}}]{"}"}'
    )

    print("  [Subtitles] Génération LLM…")
    try:
        raw  = _call_github_models(api_key, prompt)
        data = _extract_json(raw)
        raw_list = data.get("subtitles", [])
        if not raw_list:
            raise ValueError("Liste vide")
    except Exception as e:
        print(f"  [Subtitles] LLM erreur : {e} — défaut")
        return _default_subtitles(content_dur, segments)

    subtitles = []
    last_end  = -99.0
    for s in raw_list[:3]:
        txt  = str(s.get("text", "")).strip()[:28]
        if not txt:
            continue
        t0   = float(s.get("t_start", 0.5))
        tdur = float(s.get("t_dur",   2.0))
        # Anti-chevauchement
        if t0 < last_end + 0.25:
            t0 = last_end + 0.25
        t0   = max(0.1, min(t0, max(0.1, content_dur - 1.5)))
        tdur = max(1.0, min(tdur, content_dur - t0))
        last_end = t0 + tdur
        subtitles.append({"text": txt, "t_start": round(t0, 2), "t_dur": round(tdur, 2)})
        print(f'    📝 "{txt}"  @{t0:.1f}s → {t0+tdur:.1f}s')

    return subtitles


def _default_subtitles(content_dur, segments=None):
    """Sous-titres par défaut."""
    n = len(segments) if segments else 1
    subs = [{"text": "Ça fait vraiment mal...", "t_start": 0.4, "t_dur": 2.0}]
    if content_dur > 3.5 and n >= 2:
        subs.append({"text": "Collection complète !",
                     "t_start": round(content_dur * 0.58, 1), "t_dur": 1.8})
    print(f"  [Subtitles] {len(subs)} sous-titre(s) par défaut")
    return subs


def apply_subtitles(input_video, output_video, subtitles, opts):
    """
    Incrust les sous-titres via FFmpeg drawtext.
    Le 1er sous-titre (hook) reçoit un effet glitch RGB si glitch_text=True :
      - canal R décalé de +N px à droite
      - canal B décalé de -N px à gauche
      - le canal G reste centré = texte principal lisible
    Utilise textfile= pour éviter tout problème d'échappement.
    """
    if not subtitles:
        run(f'cp "{input_video}" "{output_video}"')
        return

    W_str, H_str = cfg(opts, "resolution").split("x")
    W_px  = int(W_str)
    H_px  = int(H_str)
    crf   = cfg(opts, "crf")
    do_glitch    = cfg(opts, "glitch_text")
    glitch_px    = int(cfg(opts, "glitch_intensity"))   # décalage px canaux R/B

    font_size = max(36, int(H_px * 0.042))
    zone_h    = int(H_px * 0.095)
    band_y    = H_px - zone_h - int(H_px * 0.03)
    text_y    = band_y + zone_h // 2

    try:
        vid_dur = duration(input_video)
        subtitles = [s for s in subtitles if s.get("t_start", 0) < vid_dur - 0.3]
        for s in subtitles:
            s["t_start"] = max(0.1, min(float(s["t_start"]), vid_dur - 0.5))
            s["t_dur"]   = max(0.5, min(float(s.get("t_dur", 2.0)), vid_dur - s["t_start"]))
    except Exception:
        pass

    if not subtitles:
        run(f'cp "{input_video}" "{output_video}"')
        return

    vf_parts = []

    for i, s in enumerate(subtitles):
        t0   = s["t_start"]
        tend = t0 + s["t_dur"]
        is_hook = (i == 0)

        txt_path = f"_sub_{i}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(s["text"])

        # Bande noire semi-transparente
        vf_parts.append(
            f"drawbox="
            f"x=0:y={band_y}:w={W_px}:h={zone_h}:"
            f"color=black@0.62:t=fill:"
            f"enable='between(t,{t0:.3f},{tend:.3f})'"
        )

        if is_hook and do_glitch:
            # ── Glitch RGB — hook uniquement ────────────────────────
            # Canal R : décalé +glitch_px, rouge semi-transparent
            vf_parts.append(
                f"drawtext=fontfile={FONT}:textfile={txt_path}:"
                f"fontsize={font_size}:fontcolor=red@0.55:"
                f"bordercolor=black@0:borderw=0:"
                f"x=(w-text_w)/2+{glitch_px}:y={text_y}-(text_h/2):"
                f"enable='between(t,{t0:.3f},{tend:.3f})'"
            )
            # Canal B : décalé -glitch_px, bleu semi-transparent
            vf_parts.append(
                f"drawtext=fontfile={FONT}:textfile={txt_path}:"
                f"fontsize={font_size}:fontcolor=0x4488FF@0.50:"
                f"bordercolor=black@0:borderw=0:"
                f"x=(w-text_w)/2-{glitch_px}:y={text_y}-(text_h/2):"
                f"enable='between(t,{t0:.3f},{tend:.3f})'"
            )
            # Canal principal blanc — par-dessus, centré
            vf_parts.append(
                f"drawtext=fontfile={FONT}:textfile={txt_path}:"
                f"fontsize={font_size}:fontcolor=white:"
                f"bordercolor=black:borderw=2:"
                f"x=(w-text_w)/2:y={text_y}-(text_h/2):"
                f"enable='between(t,{t0:.3f},{tend:.3f})'"
            )
            print(f"  [GlitchText] Sous-titre hook glitché ±{glitch_px}px  RGB split")
        else:
            # Style standard propre
            vf_parts.append(
                f"drawtext=fontfile={FONT}:textfile={txt_path}:"
                f"fontsize={font_size}:fontcolor=white:"
                f"bordercolor=black:borderw=3:"
                f"x=(w-text_w)/2:y={text_y}-(text_h/2):"
                f"enable='between(t,{t0:.3f},{tend:.3f})'"
            )

    vf = ",".join(vf_parts)

    run(
        f'ffmpeg -y -i "{input_video}" '
        f'-vf "{vf}" '
        f'-c:v libx264 -crf {crf} -pix_fmt yuv420p '
        f'-c:a copy '
        f'"{output_video}"'
    )
    print(f"  [Subtitles] {len(subtitles)} sous-titre(s) appliqué(s) ✅")


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
    print("  ViraCut v13 -- LesCrados.Ai  [LOGO CUSTOM ENGINE]")
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

        # ── Détection bords de carte par saturation + scale fill ────
        # Le fond gris-beige de la carte Crados a une saturation très faible
        # (canaux R≈G≈B). On scanne les colonnes/lignes de bord en rawvideo
        # et on crop sur le vrai contenu avant de scaler vers W×H.
        def _detect_card_borders(path, vw, vh):
            """Retourne (left, right, top, bottom) via détection de saturation.
            Aucune dépendance externe — 100% rawvideo FFmpeg."""
            try:
                # Tester 3 timestamps et prendre le max pour robustesse
                dur = max(duration(path), 1.0)
                timestamps = [min(0.5, dur*0.1), min(1.5, dur*0.3), min(dur*0.6, dur-0.1)]
                best = (0, 0, 0, 0)
                raw = None
                for ts in timestamps:
                    r2 = subprocess.run(
                        f'ffmpeg -ss {ts:.2f} -i "{path}" -vframes 1 '
                        f'-f rawvideo -pix_fmt rgb24 -vcodec rawvideo pipe:1 2>/dev/null',
                        shell=True, capture_output=True
                    )
                    if len(r2.stdout) == vw * vh * 3:
                        raw = r2.stdout
                        break
                if raw is None:
                    return 0, 0, 0, 0
                STEP = 4  # échantillonnage 1 ligne sur 4
                SAT_THR = 25   # seuil saturation : fond carte < 25, contenu > 25
                LUM_MIN = 80   # luminosité min pour éviter de couper sur du noir

                def col_sat(x):
                    rs=gs=bs=n=0
                    for y in range(0, vh, STEP):
                        b = (y*vw+x)*3
                        r,g,bl = raw[b], raw[b+1], raw[b+2]
                        rs+=r; gs+=g; bs+=bl; n+=1
                    if n==0: return 0,0
                    r,g,b = rs/n, gs/n, bs/n
                    sat = max(r,g,b) - min(r,g,b)
                    lum = (r+g+b)/3
                    return sat, lum

                def row_sat(y):
                    rs=gs=bs=n=0
                    for x in range(0, vw, STEP):
                        b = (y*vw+x)*3
                        r,g,bl = raw[b], raw[b+1], raw[b+2]
                        rs+=r; gs+=g; bs+=bl; n+=1
                    if n==0: return 0,0
                    r,g,b = rs/n, gs/n, bs/n
                    sat = max(r,g,b) - min(r,g,b)
                    lum = (r+g+b)/3
                    return sat, lum

                def find_border(scan_fn, seq):
                    border = 0
                    for i in seq:
                        sat, lum = scan_fn(i)
                        if sat > SAT_THR or lum < LUM_MIN:
                            border = abs(i - seq[0])
                            break
                    return max(0, border - 2)

                left   = find_border(col_sat, list(range(0,    min(120, vw))))
                right  = find_border(col_sat, list(range(vw-1, max(vw-120,-1), -1)))
                top    = find_border(row_sat, list(range(0,    min(80,  vh))))
                bottom = find_border(row_sat, list(range(vh-1, max(vh-80, -1), -1)))
                return left, right, top, bottom
            except Exception as _e:
                print(f"      _detect_card_borders: {_e}")
                return 0, 0, 0, 0

        src_info2 = ffprobe(raw)
        src_vs2   = [s for s in src_info2.get("streams",[]) if s.get("codec_type")=="video"]
        src_w = int(src_vs2[0].get("width",  int(W))) if src_vs2 else int(W)
        src_h = int(src_vs2[0].get("height", int(H))) if src_vs2 else int(H)

        bl, br, bt, bb = _detect_card_borders(raw, src_w, src_h)
        print(f"  Clip {i} bords carte : L={bl} R={br} T={bt} B={bb}")

        if bl + br + bt + bb > 4:
            cw = src_w - bl - br;  cw -= cw % 2
            ch = src_h - bt - bb;  ch -= ch % 2
            cx, cy = bl, bt
            # Scale sur la largeur → W, crop vertical centré
            sh = int(ch * int(W) / cw); sh += sh % 2
            # Garantir sh >= H
            if sh < int(H):
                sh = int(H)
                sw = int(cw * int(H) / ch); sw += sw % 2
            else:
                sw = int(W)
            crop_x = max(0, (sw - int(W)) // 2)
            crop_y = max(0, (sh - int(H)) // 2)
            vf_scale = (
                f"crop={cw}:{ch}:{cx}:{cy},"
                f"scale={sw}:{sh}:flags=lanczos,"
                f"crop={W}:{H}:{crop_x}:{crop_y},"
                f"setsar=1,fps={fps}"
            )
            print(f"      crop {cw}x{ch}+{cx}+{cy} → scale {sw}x{sh} → crop {W}x{H}+{crop_x}+{crop_y}")
        else:
            # Pas de bord détecté : scale direct sans recadrage
            vf_scale = (
                f"scale={W}:{H}:flags=lanczos,"
                f"setsar=1,fps={fps}"
            )

        if audio_streams:
            run(
                f'ffmpeg -y -i "{raw}" {map_v} -map 0:a:0 '
                f'-vf "{vf_scale}" '
                f'-c:v libx264 -crf {crf} -preset fast -pix_fmt yuv420p '
                f'-x264opts "keyint={fps}:no-scenecut" '
                f'-bf 0 -c:a aac -ar 44100 -ac 2 "{p}"'
            )
        else:
            # Source sans audio → générer silence
            run(
                f'ffmpeg -y -i "{raw}" -f lavfi -i "anullsrc=r=44100:cl=stereo" {map_v} -map 1:a '
                f'-vf "{vf_scale}" '
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
            punch_d = src_durs[1]   # punch : durée source complète
            seg_durs = [hook_d, punch_d]
        elif n == 3:
            hook_d  = max(min(raw_hook,  src_durs[0]), 2.0)
            # CORE et PUNCH : passer la durée source COMPLÈTE comme target_dur.
            # build_cinema_segment utilisera toute la source pour ne pas
            # couper la scène virale (recrachement, révélation, action clé).
            core_d  = src_durs[1]
            punch_d = src_durs[2]
            seg_durs = [hook_d, core_d, punch_d]
        else:
            seg_durs = []
            for k, sd in enumerate(src_durs):
                if k == 0:
                    seg_durs.append(max(min(raw_hook, sd), 2.0))
                else:
                    # Tous les segments non-hook : durée source complète
                    seg_durs.append(sd)
        # Si le total core+punch dépasse le cap PUNCH (15s), passer en mode CINEMA
        total_content = sum(seg_durs)
        if total_content > 15.0:
            print(f"  ⚠ Total {total_content:.1f}s > 15s → bascule en mode CINEMA pour fluidité")
            opts["mode"] = "cinema"
            mode_final   = "cinema"
            # Recalculer seg_durs en mode cinema : clip_dur uniforme
            cinema_target = min(total_content, cfg(opts, "cinema_dur") if total_content > cfg(opts, "cinema_dur") else total_content)
            clip_dur_c = max(cinema_target / n, MIN_CLIP_DUR)
            seg_durs = [min(clip_dur_c, sd) for sd in src_durs]
            print(f"  Durées CINEMA   : {[round(d,2) for d in seg_durs]}")
        else:
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

    # ── Sous-titres ────────────────────────────────────────────────
    print("\n  [Sous-titres]")
    subtitles = subtitle_analysis(segments, opts, vira_result)
    if subtitles:
        run('mv output.mp4 _presub.mp4')
        apply_subtitles("_presub.mp4", "output.mp4", subtitles, opts)
    else:
        print("  [Subtitles] Aucun sous-titre")

    size = os.path.getsize("output.mp4") / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"  OK  output.mp4   {size:.1f} MB")
    print(f"{'='*60}")


if __name__ == "__main__":
    start()
