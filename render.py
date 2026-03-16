"""
render.py — ViraCut Studio v10  ★ LesCrados.Ai Edition ★  [Logo Pixar-style v2]
═════════════════════════════════════════════════════════
v10 : VIRALITÉ ANALYSIS ENGINE
     — analyse Claude API avant rendu FFmpeg
     — score 0-100 + 5 axes + recommandations
     — résultat JSON dans les logs GitHub Actions (parsé par App.html)
v9  : DIALOGUE CUT ENGINE
     — silencedetect FFmpeg pour trouver les pauses naturelles
     — snap OUT : raccord à la pause la plus proche de la cible
     — snap IN  : entrée après la première pause (pas de mot coupé)
     — xfade adaptatif : durée ajustée selon contexte audio
     — fallback propre si pas d'audio / pas de silence trouvé
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
    "dialogue_cut":       False,  # OFF — clips AI sans pauses audio détectables
    "dialogue_noise_db":  -28,    # seuil de silence (dBFS)
    "dialogue_min_pause": 0.08,   # duree min d une pause (s)
    "dialogue_tolerance": 1.5,    # fenetre +/-s autour de la cible
    "dialogue_in_snap":   False,  # désactivé — snap IN coupe le début de l'action
    "dialogue_xfade_min": 0.15,   # xfade court si coupure en plein dialogue
    "dialogue_xfade_max": 0.35,   # xfade long si coupure en silence
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
        f'-c:v libx264 -pix_fmt yuv420p -crf {cfg(opts, "crf")} output.mp4'
    )


# ═══════════════════════════════════════════════════════════════════════
# SEGMENTS CINEMA + DIALOGUE SNAP
# ═══════════════════════════════════════════════════════════════════════
def build_cinema_segment(src, seg_out, target_dur, kb_zoom, opts):
    """
    Extrait un segment depuis src avec :
      - snap IN  : point d entree apres la premiere pause audio
      - snap OUT : point de sortie cale sur la pause la plus proche
      - Ken Burns + grade + pad sans coupure de bords
    Retourne un dict avec les metadonnees du segment.
    """
    W, H    = cfg(opts, "resolution").split("x")
    fps     = cfg(opts, "fps")
    crf     = cfg(opts, "crf")
    src_dur = duration(src)

    use_dialogue = cfg(opts, "dialogue_cut")
    noise_db     = cfg(opts, "dialogue_noise_db")
    min_pause    = cfg(opts, "dialogue_min_pause")
    tolerance    = cfg(opts, "dialogue_tolerance")
    do_in_snap   = cfg(opts, "dialogue_in_snap")

    # ── Detection des silences ───────────────────────────────────────
    silences = detect_silences(src, noise_db, min_pause) if use_dialogue else []
    if silences:
        print(f"      Silences detectes : {len(silences)}"
              f"  (1er: [{silences[0][0]:.2f}-{silences[0][1]:.2f}]s)")
    else:
        print(f"      Aucun silence (seuil {noise_db}dB min {min_pause}s) -> cut brut")

    # ── Snap IN ──────────────────────────────────────────────────────
    if use_dialogue and do_in_snap and silences:
        in_pt, in_lbl = find_cut_in(silences, src_dur)
    else:
        in_pt, in_lbl = 0.0, "disabled"

    # Recalibrer les silences en coordonnees locales (apres in_pt)
    local_silences = []
    for (s, e) in silences:
        ls = s - in_pt
        le = e - in_pt
        if le > 0 and ls < target_dur + tolerance:
            local_silences.append((max(0.0, ls), le))

    # ── Snap OUT ─────────────────────────────────────────────────────
    clip_max = max(src_dur - in_pt, 1.0)

    if use_dialogue and local_silences:
        actual, out_lbl = find_cut_out(local_silences, target_dur, clip_max, tolerance)
    else:
        actual  = min(target_dur, clip_max)
        out_lbl = "no_silence"

    actual = max(actual, 1.0)  # garde-fou absolu

    # ── Filtres video ────────────────────────────────────────────────
    # Pas de scale ici — déjà fait en sanitisation à la réception des clips
    # Uniquement fps et grade colorimétrique — style BD/carte collector Les Crados
    # saturation légèrement boostée + contraste plus marqué pour look punchy
    grade = "eq=saturation=1.10:brightness=-0.02:contrast=1.12,hue=h=0:s=1"
    vf = f"fps={fps},{grade}"

    # ── Extraction (avec seek en entree = ultra rapide) ───────────────
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
        "silences": local_silences,
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
# STICKER ENGINE  (v1) — Génération PNG + overlay FFmpeg animé
# ═══════════════════════════════════════════════════════════════════════
import math as _math

def _gen_sticker_png(stype, text, color_hex, size, out_path):
    """
    Génère un sticker PNG RGBA via Pillow.
    Contour noir épais + ombre portée pour visibilité sur fond chargé.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        return False

    # Canvas plus grand pour laisser de la place à l'ombre
    PAD = max(12, size // 14)
    W = H = size + PAD * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    cx, cy = W // 2, H // 2
    # Fond blanc semi-opaque arrondi = toujours visible sur n'importe quel fond
    bg_r = max(10, W // 8)
    d.rounded_rectangle([PAD//2, PAD//2, W-PAD//2, H-PAD//2],
                         radius=bg_r, fill=(255, 255, 255, 160))

    ch = color_hex.lstrip("#")
    cr, cg, cb = int(ch[0:2],16), int(ch[2:4],16), int(ch[4:6],16)
    col_main  = (cr, cg, cb, 255)
    col_dark  = (max(0,cr-80), max(0,cg-80), max(0,cb-80), 255)
    col_light = (min(255,cr+100), min(255,cg+100), min(255,cb+100), 200)
    stroke    = (0, 0, 0, 255)  # contour noir

    r_base = int(size * 0.38)

    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", max(16, size//4))
        font_sm  = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", max(12, size//6))
    except Exception:
        font_big = font_sm = ImageFont.load_default()

    def draw_stroke_ellipse(draw, bbox, fill, stroke_col, stroke_w=4):
        sw = stroke_w
        draw.ellipse([bbox[0]-sw, bbox[1]-sw, bbox[2]+sw, bbox[3]+sw], fill=stroke_col)
        draw.ellipse(bbox, fill=fill)

    if stype == "splat":
        import random as _rnd
        _rnd.seed(hash(text or "splat") % 9999)
        r = r_base
        # Ombre
        shadow = Image.new("RGBA", (W, H), (0,0,0,0))
        sd = ImageDraw.Draw(shadow)
        sd.ellipse([cx-r+4, cy-r+6, cx+r+4, cy+r+6], fill=(0,0,0,100))
        img.alpha_composite(shadow)
        d = ImageDraw.Draw(img)
        # Contour
        d.ellipse([cx-r-5, cy-r-5, cx+r+5, cy+r+5], fill=stroke)
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=col_main)
        for angle_deg in range(0, 360, 28):
            angle = _math.radians(angle_deg + _rnd.randint(-12,12))
            dist = r + _rnd.randint(int(size*0.08), int(size*0.18))
            bx = cx + int(dist * _math.cos(angle))
            by = cy + int(dist * _math.sin(angle))
            br = _rnd.randint(int(size*0.06), int(size*0.12))
            d.ellipse([bx-br-3, by-br-3, bx+br+3, by+br+3], fill=stroke)
            d.ellipse([bx-br, by-br, bx+br, by+br], fill=col_main)
        d.ellipse([cx-r//3, cy-r//2, cx, cy-r//6], fill=col_light)
        if text:
            # Stroke texte
            for dx,dy in [(-2,0),(2,0),(0,-2),(0,2)]:
                d.text((cx+dx, cy+dy), text[:10], fill=stroke, font=font_big, anchor="mm")
            d.text((cx, cy), text[:10], fill=(255,255,255,255), font=font_big, anchor="mm")

    elif stype == "impact":
        rings = [(220,50,0,230),(255,130,0,190),(255,210,0,150),(255,255,100,110)]
        for i, rc in enumerate(rings):
            r = int(size*0.44) - i*int(size*0.09)
            lw = max(3, int(size*0.032)) - i
            # Contour noir
            d.ellipse([cx-r-lw-2, cy-r-lw-2, cx+r+lw+2, cy+r+lw+2], outline=(0,0,0,200), width=lw+2)
            d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=rc, width=lw)
        d.ellipse([cx-int(size*0.09)-3, cy-int(size*0.09)-3,
                   cx+int(size*0.09)+3, cy+int(size*0.09)+3], fill=stroke)
        d.ellipse([cx-int(size*0.09), cy-int(size*0.09),
                   cx+int(size*0.09), cy+int(size*0.09)], fill=(255,60,0,255))

    elif stype == "bubble":
        bx, by = PAD, PAD
        bw, bh = int(size*0.84), int(size*0.60)
        # Ombre
        d.rounded_rectangle([bx+4, by+6, bx+bw+4, by+bh+6], radius=int(size*0.09), fill=(0,0,0,120))
        # Contour noir
        d.rounded_rectangle([bx-3, by-3, bx+bw+3, by+bh+3], radius=int(size*0.10),
                             fill=stroke)
        d.rounded_rectangle([bx, by, bx+bw, by+bh], radius=int(size*0.09),
                             fill=(255,255,255,245))
        tail = [(bx+int(bw*0.15), by+bh), (bx+int(bw*0.40), by+bh),
                (bx+int(bw*0.08), by+bh+int(size*0.22))]
        d.polygon([(p[0]-2,p[1]+2) for p in tail], fill=stroke)
        d.polygon(tail, fill=(255,255,255,245))
        if text:
            lines = text.split(" ")
            mid = max(1, len(lines)//2)
            l1, l2 = " ".join(lines[:mid]), " ".join(lines[mid:])
            ty = by + bh//2 - (int(size*0.07) if l2 else 0)
            for dx,dy in [(-2,0),(2,0),(0,-2),(0,2)]:
                d.text((bx+bw//2+dx, ty+dy), l1, fill=stroke, font=font_big, anchor="mm")
            d.text((bx+bw//2, ty), l1, fill=(200,0,0,255), font=font_big, anchor="mm")
            if l2:
                for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    d.text((bx+bw//2+dx, ty+int(size*0.16)+dy), l2, fill=stroke, font=font_sm, anchor="mm")
                d.text((bx+bw//2, ty+int(size*0.16)), l2, fill=(40,40,40,255), font=font_sm, anchor="mm")

    elif stype == "star":
        pts = []
        for i in range(16):
            angle = _math.radians(i * 22.5 - 90)
            r = int(size*0.44) if i%2==0 else int(size*0.24)
            pts.append((cx + r*_math.cos(angle), cy + r*_math.sin(angle)))
        # Ombre
        shadow_pts = [(x+4, y+5) for x,y in pts]
        d.polygon(shadow_pts, fill=(0,0,0,100))
        # Contour
        outline_pts = [(cx + (r+4)*_math.cos(_math.radians(i*22.5-90)),
                        cy + (r+4)*_math.sin(_math.radians(i*22.5-90)))
                       for i,r in [(i, int(size*0.44) if i%2==0 else int(size*0.24))
                                   for i in range(16)]]
        d.polygon(outline_pts, fill=stroke)
        d.polygon(pts, fill=(255,220,0,250))
        if text:
            parts = text.split(" ", 1)
            for dx,dy in [(-2,0),(2,0),(0,-2),(0,2)]:
                d.text((cx+dx, cy-int(size*0.07)+dy), parts[0][:8], fill=stroke, font=font_big, anchor="mm")
            d.text((cx, cy-int(size*0.07)), parts[0][:8], fill=(200,0,0,255), font=font_big, anchor="mm")
            if len(parts)>1:
                for dx,dy in [(-1,0),(1,0)]:
                    d.text((cx+dx, cy+int(size*0.12)+dy), parts[1][:8], fill=stroke, font=font_sm, anchor="mm")
                d.text((cx, cy+int(size*0.12)), parts[1][:8], fill=(30,30,30,255), font=font_sm, anchor="mm")

    elif stype == "zap":
        zap = [
            (int(W*0.55),int(H*0.05)), (int(W*0.28),int(H*0.50)),
            (int(W*0.50),int(H*0.50)), (int(W*0.22),int(H*0.95)),
            (int(W*0.72),int(H*0.44)), (int(W*0.50),int(H*0.44)),
            (int(W*0.72),int(H*0.05))
        ]
        shadow_zap = [(x+3, y+4) for x,y in zap]
        d.polygon(shadow_zap, fill=(0,0,0,130))
        stroke_zap = [(int(W*0.55)-3,int(H*0.05)-3),(int(W*0.28)-3,int(H*0.50)),(int(W*0.50)-3,int(H*0.50)),
                      (int(W*0.22)-3,int(H*0.95)+3),(int(W*0.72)+3,int(H*0.44)),(int(W*0.50)+3,int(H*0.44)),
                      (int(W*0.72)+3,int(H*0.05)-3)]
        d.polygon(stroke_zap, fill=stroke)
        d.polygon(zap, fill=(255,240,0,255))

    elif stype == "arrow":
        pts_a = [
            (int(W*0.92),int(H*0.36)),(int(W*0.92),int(H*0.64)),
            (int(W*0.45),int(H*0.64)),(int(W*0.45),int(H*0.82)),
            (int(W*0.08),cy),
            (int(W*0.45),int(H*0.18)),(int(W*0.45),int(H*0.36))
        ]
        shadow_a = [(x+3, y+4) for x,y in pts_a]
        d.polygon(shadow_a, fill=(0,0,0,130))
        stroke_a = [(x-2 if x<cx else x+2, y-2 if y<cy else y+2) for x,y in pts_a]
        d.polygon(stroke_a, fill=stroke)
        d.polygon(pts_a, fill=col_main)

    # Léger flou sur l'ombre portée pour adoucir
    img.save(out_path)
    return True



def _sticker_overlay_filter(stickers, video_w, video_h):
    """
    Filter_complex FFmpeg — overlay PNG stickers avec fade alpha via loop+trim.
    Approche robuste : chaque PNG est loopé sur toute la durée vidéo,
    le timing est géré par enable + fade filter local.
    """
    if not stickers:
        return [], "", 0

    input_args  = []
    filter_parts = []
    prev_label  = "0:v"
    nb_ok = 0

    for idx, s in enumerate(stickers):
        img_path = f"_sticker_{idx}.png"
        stype = s.get("type",   "star")
        text  = s.get("text",   "")
        color = s.get("color",  "#FF2200")
        sz    = s.get("size",   int(video_w * 0.28))
        x_pct = s.get("x_pct", 0.82)
        y_pct = s.get("y_pct", 0.38)
        t0    = float(s.get("t_start", 0.8))
        tdur  = float(s.get("t_dur",   1.3))
        anim  = s.get("anim",   "pop")

        ok = _gen_sticker_png(stype, text, color, sz, img_path)
        if not ok:
            continue

        # Clamp position dans la zone visible (hors letterbox 65px)
        lb, margin = 65, 15
        px = int(video_w  * x_pct - sz / 2)
        py = int(video_h * y_pct - sz / 2)
        px = max(margin, min(px, video_w  - sz - margin))
        py = max(lb + margin, min(py, video_h - lb - sz - margin))

        t_end    = t0 + tdur
        fade_in  = min(0.12, tdur * 0.15)
        fade_out = min(0.15, tdur * 0.18)
        hold     = max(0.1, tdur - fade_in - fade_out)
        enable   = f"between(t,{t0:.3f},{t_end:.3f})"

        # Chaîne de filtre sur le PNG :
        # 1. scale à la bonne taille
        # 2. loop pour couvrir toute la durée de la vidéo (999 frames suffit)
        # 3. fade in puis fade out (en temps local depuis le début du PNG)
        # 4. setpts pour décaler le début au bon moment dans la timeline
        vf_sticker = (
            f"[{idx+1}:v]"
            f"scale={sz}:{sz}:flags=lanczos,"
            f"format=rgba,"
            f"loop=loop=-1:size=1,"
            f"trim=start=0:end={tdur:.3f},"
            f"fade=t=in:st=0:d={fade_in:.3f}:alpha=1,"
            f"fade=t=out:st={fade_in+hold:.3f}:d={fade_out:.3f}:alpha=1,"
            f"setpts=PTS+{t0:.3f}/TB"
            f"[s{idx}]"
        )
        overlay_f = (
            f"[{prev_label}][s{idx}]"
            f"overlay=x={px}:y={py}:format=auto:enable='{enable}'"
            f"[v{idx}]"
        )

        filter_parts.append(vf_sticker)
        filter_parts.append(overlay_f)
        prev_label = f"v{idx}"
        input_args.extend(["-i", img_path])
        nb_ok += 1

    if not filter_parts:
        return [], "", 0

    # Assembler le filter_complex et renommer le dernier [vN] en [vout]
    last_label = f"[v{nb_ok-1}]"
    chain = ";".join(filter_parts)
    # Remplacer la dernière occurrence du label final par [vout]
    last_idx = chain.rfind(last_label)
    if last_idx != -1:
        final_filter = chain[:last_idx] + "[vout]" + chain[last_idx+len(last_label):]
    else:
        final_filter = chain
    return input_args, final_filter, nb_ok



def sticker_analysis(segments, opts, vira_result):
    """
    Demande au LLM de placer des stickers intelligents.
    Retourne une liste de sticker dicts, ou des stickers par défaut si LLM absent/echec.
    """
    api_key = os.environ.get("GITHUB_TOKEN", "")

    if not opts.get("stickers", True):
        print("  [Stickers] Désactivés par config")
        return []

    W, H = cfg(opts, "resolution").split("x")
    W_px = int(W)

    # Durée de contenu réel (sans logo 2.5s)
    content_dur = sum(s["dur"] for s in segments)

    # Construire le résumé des segments avec timecodes absolus
    segs_lines = []
    t_cursor = 0.0
    for i, s in enumerate(segments):
        role = "hook" if i == 0 else ("punch" if i == len(segments)-1 else "core")
        segs_lines.append(
            f"  Segment {i+1} : t={t_cursor:.1f}s→{t_cursor+s['dur']:.1f}s  "
            f"durée={s['dur']:.2f}s  rôle={role}"
        )
        t_cursor += s["dur"]
    segs_desc = "\n".join(segs_lines)

    vira_recs = ""
    if vira_result:
        recs = vira_result.get("recs", [])
        vira_recs = "  Viralité : " + " | ".join(r["text"] for r in recs[:3])

    if not api_key:
        print("  [Stickers] GITHUB_TOKEN absent — stickers par défaut")
        return _default_stickers(W_px, content_dur)

    prompt = (
        f"Tu es un expert TikTok Les Crados (cartes satiriques style Garbage Pail Kids).\n"
        f"Place des stickers animés pour amplifier l'impact. Vidéo = {content_dur:.1f}s (hors logo).\n\n"
        f"SEGMENTS :\n{segs_desc}\n{vira_recs}\n\n"
        f"STICKERS : splat (slime), impact (ondes choc), bubble (texte bulle ≤12 chars), "
        f"star (texte exclamation ≤8 chars), zap (éclair)\n\n"
        f"RÈGLES : 2-3 stickers · t_start < {content_dur-1.0:.1f}s · "
        f"x_pct < 0.25 ou > 0.75 (bords) · size_pct 0.24-0.32 · t_dur 1.0-1.8s\n\n"
        f"JSON UNIQUEMENT :\n"
        f"{{\"stickers\": [{{"
        f"\"type\":\"<splat|impact|bubble|star|zap>\","
        f"\"text\":\"<vide ou texte>\"," 
        f"\"color\":\"<hex>\","
        f"\"size_pct\":<float>,"
        f"\"x_pct\":<float>,"
        f"\"y_pct\":<float>,"
        f"\"t_start\":<float>,"
        f"\"t_dur\":<float>"
        f"}}]}}"
    )

    print("  [Stickers] Analyse IA en cours…")
    try:
        raw = _call_github_models(api_key, prompt)
        data = _extract_json(raw)
        stickers_raw = data.get("stickers", [])
        if not stickers_raw:
            raise ValueError("Liste vide")
    except Exception as e:
        print(f"  [Stickers] Erreur API : {e} — stickers par défaut")
        return _default_stickers(W_px, content_dur)

    stickers = []
    for s in stickers_raw[:3]:
        sz = max(200, min(300, int(W_px * float(s.get("size_pct", 0.28)))))
        t0 = min(float(s.get("t_start", 1.0)), max(0.5, content_dur - 1.5))
        stickers.append({
            "type":    s.get("type",  "star"),
            "text":    s.get("text",  ""),
            "color":   s.get("color", "#FF2200"),
            "size":    sz,
            "x_pct":   float(s.get("x_pct",  0.82)),
            "y_pct":   float(s.get("y_pct",  0.25)),
            "t_start": t0,
            "t_dur":   min(float(s.get("t_dur", 1.3)), content_dur - t0),
            "anim":    "pop",
        })
        print(f"    🎯 {stickers[-1]['type']:8s} @ {t0:.1f}s  pos=({stickers[-1]['x_pct']:.2f},{stickers[-1]['y_pct']:.2f})")

    return stickers


def _default_stickers(W_px, content_dur):
    """Stickers par défaut quand le LLM n'est pas disponible."""
    if content_dur < 2.0:
        return []
    sz = max(220, int(W_px * 0.32))  # 32% de largeur = ~230px sur 720p
    stickers = [
        # Coin haut-droite — splat orange vif (contraste avec les cartes sombres/vertes)
        {"type":"splat","text":"","color":"#FF6600","size":sz,
         "x_pct":0.84,"y_pct":0.38,"t_start":min(0.8,content_dur*0.12),"t_dur":1.3,"anim":"pop"},
    ]
    if content_dur > 4.0:
        # Côté gauche milieu — zap jaune électrique (visible sur tout fond)
        stickers.append(
            {"type":"zap","text":"","color":"#FFE000","size":sz,
             "x_pct":0.20,"y_pct":0.45,"t_start":content_dur*0.55,"t_dur":1.1,"anim":"pop"}
        )
    print(f"  [Stickers] {len(stickers)} sticker(s) par défaut appliqués")
    return stickers

def apply_stickers(input_video, output_video, stickers, opts):
    """
    Applique les stickers animés sur la vidéo via FFmpeg overlay.
    """
    if not stickers:
        run(f'cp "{input_video}" "{output_video}"')
        return

    W_str, H_str = cfg(opts, "resolution").split("x")
    W_px = int(W_str)
    H_px = int(H_str)
    crf  = cfg(opts, "crf")

    # Valider les stickers : cap t_start à la durée de la vidéo - 1s
    try:
        vid_dur = duration(input_video)
        stickers = [s for s in stickers
                    if s.get("t_start", 0) < vid_dur - 0.5]
        for s in stickers:
            s["t_start"] = max(0.1, min(s["t_start"], vid_dur - 1.0))
        if not stickers:
            print("  [Stickers] Tous les stickers hors durée — ignorés")
            run(f'cp "{input_video}" "{output_video}"')
            return
    except Exception:
        pass  # si durée non lisible, on continue quand même

    input_args, filter_str, nb = _sticker_overlay_filter(stickers, W_px, H_px)

    if not filter_str:
        run(f'cp "{input_video}" "{output_video}"')
        return

    inputs = f'"{input_video}"' + " " + " ".join(f'"{a}"' if not a.startswith("-") else a for a in input_args)
    # Reconstruire proprement
    cmd_parts = [f'ffmpeg -y -i "{input_video}"']
    for a in input_args:
        cmd_parts.append(a)

    cmd = (
        "ffmpeg -y"
        + f' -i "{input_video}"'
        + " " + " ".join(input_args)
        + f' -filter_complex "{filter_str}"'
        + f' -map "[vout]" -map "0:a:0" -c:v libx264 -crf {crf} -c:a copy "{output_video}"'
    )
    try:
        run(cmd)
        print(f"  [Stickers] {nb} sticker(s) appliqué(s) ✅")
    except Exception as e:
        print(f"  [Stickers] ERREUR DÉTAILLÉE : {e}")
        print(f"  [Stickers] CMD était : {cmd[:300]}")
        print(f"  [Stickers] Fallback cp — output sans stickers")
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
    print("  ViraCut v11 -- LesCrados.Ai  [CONCAT CUT ENGINE]")
    print("=" * 60)
    print(f"  Clips recus        : {len(clips_raw)}")
    print(f"  Dialogue cut       : {cfg(opts,'dialogue_cut')}")
    print(f"  Bruit seuil        : {cfg(opts,'dialogue_noise_db')} dBFS")
    print(f"  Pause min          : {cfg(opts,'dialogue_min_pause')}s")
    print(f"  Tolerance snap     : +/-{cfg(opts,'dialogue_tolerance')}s")
    print(f"  Snap IN            : {cfg(opts,'dialogue_in_snap')}")
    print(f"  xfade dialogue  : {cfg(opts,'dialogue_xfade_min')}-{cfg(opts,'dialogue_xfade_max')}s")

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
        print(f"{'─'*55}")
        print(f"  [Segment {i+1}/{n}  cible={sdur:.2f}s]")
        seg = build_cinema_segment(src, out, sdur,
                                   1.0, opts)  # HARDCODE kb_zoom=1.0 — pas de zoom sur clips AI
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
