"""
render.py — ViraCut Studio v10  ★ LesCrados.Ai Edition ★
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
    "cinema_xfade":    0.8,
    "cinema_kb_zoom":  1.015,
    "cinema_lb_h":     80,

    # ── Dialogue Cut Engine ─────────────────────────────────────────
    "dialogue_cut":       True,   # activer le snap sur les pauses
    "dialogue_noise_db":  -30,    # seuil de silence (dBFS)
    "dialogue_min_pause": 0.08,   # duree min d une pause (s)
    "dialogue_tolerance": 1.0,    # fenetre +/-s autour de la cible
    "dialogue_in_snap":   True,   # snap aussi le point d entree
    "dialogue_xfade_min": 0.25,   # xfade court si coupure en plein dialogue
    "dialogue_xfade_max": 0.6,    # xfade long si coupure en silence
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
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps"); crf = cfg(opts, "crf")
    Wi, Hi = int(W), int(H)
    # Outro réduite à 1s — rapide, percutante, ne casse pas le rythme
    dur = 1.0
    les_sz, crados_sz, ai_sz = 60, 110, 64
    total_h   = les_sz + 14 + crados_sz + 10 + ai_sz
    block_top = (Hi - total_h) // 2
    les_y    = block_top
    crados_y = block_top + les_sz + 14
    ai_y     = block_top + les_sz + 14 + crados_sz + 16

    dt_les  = (f"drawtext=fontfile={FONT}:text='LES':fontsize={les_sz}:"
               f"fontcolor=white:x=(w-text_w)/2:y={les_y}:enable='gte(t,0)'")
    dt_crad = (f"drawtext=fontfile={FONT}:text='CRADOS':fontsize={crados_sz}:"
               f"fontcolor=white:x=(w-text_w)/2:y={crados_y}:enable='gte(t,0)'")
    dt_ai   = (f"drawtext=fontfile={FONT}:text='.Ai':fontsize={ai_sz}:"
               f"fontcolor=#FF2442:x=(w-text_w)/2:y={ai_y}:enable='gte(t,0)'")

    vf = f"{dt_les},{dt_crad},{dt_ai},fade=t=in:st=0:d=0.1,fade=t=out:st=0.8:d=0.2"
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
    # Crop intelligent : remplit le 9:16 sans barres noires
    # 1) scale pour que la plus petite dimension remplisse le cadre
    # 2) crop centré pour couper les bords excédentaires
    scale_crop = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},fps={fps}"
    )
    grade = "eq=saturation=0.95:brightness=-0.01:contrast=1.05"
    inc   = (kb_zoom - 1.0) / max(actual * fps, 1)
    kb    = (
        f"zoompan=z='min(zoom+{inc:.6f},{kb_zoom})':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
    )
    vf = f"{scale_crop},{grade},{kb}"

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
    Assemble les segments avec xfade adaptatif par transition.
    """
    seg_paths = [s["path"] for s in segments]

    if len(seg_paths) == 1:
        run(f'cp "{seg_paths[0]}" _assembled.mp4')
        return

    xf_base = cfg(opts, "cinema_xfade")
    xf_min  = cfg(opts, "dialogue_xfade_min")
    xf_max  = cfg(opts, "dialogue_xfade_max")
    use_dlg = cfg(opts, "dialogue_cut")

    inputs   = " ".join(f'-i "{p}"' for p in seg_paths)
    v_parts, a_parts = [], []
    offset   = duration(seg_paths[0])
    prev_v, prev_a = "[0:v]", "[0:a]"

    for i in range(1, len(seg_paths)):
        is_last = (i == len(seg_paths) - 1)
        nv = "[vfin]" if is_last else f"[xv{i}]"
        na = "[afin]" if is_last else f"[xa{i}]"

        out_sil    = segments[i - 1]["silences"]
        in_sil     = segments[i]["silences"]
        cut_out_t  = segments[i - 1]["dur"]

        if use_dlg:
            print(f"\n  [Transition {i-1}->{i}]")
            xf = adaptive_xfade(out_sil, in_sil, cut_out_t, xf_base, xf_min, xf_max)
        else:
            xf = xf_base

        # Garde-fous : xfade ne peut pas depasser 80% de chaque clip
        xf = min(xf,
                 duration(seg_paths[i - 1]) * 0.8,
                 duration(seg_paths[i]) * 0.8)
        xf = max(xf, 0.10)

        offset -= xf
        v_parts.append(
            f"{prev_v}[{i}:v]xfade=transition=fade:"
            f"duration={xf:.3f}:offset={offset:.3f}{nv}"
        )
        a_parts.append(f"{prev_a}[{i}:a]acrossfade=d={xf:.3f}{na}")
        offset  += duration(seg_paths[i])
        prev_v, prev_a = nv, na

    fc = ";".join(v_parts + a_parts)
    run(
        f'ffmpeg -y {inputs} -filter_complex "{fc}" '
        f'-map "[vfin]" -map "[afin]" -c:v libx264 -crf {cfg(opts,"crf")} _assembled.mp4'
    )


def build_cinema_overlay_no_text(opts):
    W, H    = cfg(opts, "resolution").split("x")
    Hi      = int(H)
    lb_h    = cfg(opts, "cinema_lb_h")
    total   = duration("_assembled.mp4")
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
# VIRALITÉ ANALYSIS ENGINE  (v10)
# ═══════════════════════════════════════════════════════════════════════
VIRALITE_MARKER_START = "##VIRALITE_JSON_START##"
VIRALITE_MARKER_END   = "##VIRALITE_JSON_END##"

def viralite_analysis(clips_raw, opts, raw_paths):
    """
    Analyse le potentiel viral TikTok des clips AVANT rendu.
    Appelle Gemini 1.5 Flash via GEMINI_API_KEY (env var GitHub Actions).
    Écrit le résultat entre markers dans stdout pour parsing App.html.
    """
    api_key = os.environ.get("GITHUB_TOKEN", "")
    if not api_key:
        print("  [Viralité] GITHUB_TOKEN absent — analyse ignorée")
        return

    print("\n  [Viralité] Analyse en cours…")

    # Métadonnées clips (sans bytes vidéo)
    clips_meta = []
    for i, (v, path) in enumerate(zip(clips_raw, raw_paths)):
        try:
            dur = duration(path)
            audio = has_audio(path)
        except Exception:
            dur, audio = 0, False
        clips_meta.append({
            "index":    i + 1,
            "role":     v.get("role", "auto"),
            "dur_s":    round(dur, 2),
            "has_audio": audio,
            "size_mb":  round(len(base64.b64decode(v["data"])) / 1_048_576, 2)
        })

    mode = opts.get("mode", "auto")
    prompt = f"""Tu es un expert TikTok spécialisé dans le contenu Les Crados (cartes satiriques style Garbage Pail Kids, humour absurde, personnages français).

Analyse ce montage et donne un score de potentiel viral TikTok.

CLIPS ({len(clips_meta)}) :
{json.dumps(clips_meta, ensure_ascii=False)}

MODE : {mode.upper()}
CONFIG : hook={opts.get("hook_dur",2)}s | core={opts.get("core_dur",2.5)}s | punch={opts.get("punch_dur",3)}s | résolution={opts.get("resolution","720x1280")} | textes_IA={opts.get("ai_text",True)} | dialogue_cut={opts.get("dialogue_cut",True)}

Évalue selon 5 axes pour Les Crados TikTok :
1. Structure narrative (hook/core/punchline)
2. Rythme & durée totale
3. Potentiel de loop (fin → début)
4. Diversité visuelle (clips variés)
5. Compatibilité format 9:16 TikTok

Réponds UNIQUEMENT en JSON valide, aucun texte avant/après :
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
    {{"type": "pos", "text": "<point fort, max 60 chars>"}},
    {{"type": "neg", "text": "<point faible, max 60 chars>"}},
    {{"type": "tip", "text": "<conseil actionnable, max 60 chars>"}}
  ]
}}"""

    payload = json.dumps({
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": 800,
        "messages":   [{"role": "user", "content": prompt}]
    }).encode()

    models = ["meta-llama-3.3-70b-instruct","gpt-4o-mini","mistral-nemo","meta-llama-3.1-8b-instruct"]
    raw_text = None
    last_err = None
    for model in models:
        payload_base = {"model":model,"messages":[{"role":"user","content":prompt[:3000]}],"temperature":0.3,"max_tokens":1200}
        req = urllib.request.Request(
            "https://models.inference.ai.azure.com/chat/completions",
            data=json.dumps(payload_base).encode(),
            headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
            raw_text = body["choices"][0]["message"]["content"]
            print(f"      Modèle : {model}")
            break
        except Exception as e:
            print(f"      {model} → {e}")
            last_err = e
    if raw_text is None:
        raise last_err

    try:
        _ = raw_text  # already set above
        clean    = raw_text.strip().lstrip("```json").rstrip("```").strip()
        result   = json.loads(clean)
        result["clips"] = len(clips_meta)
        result["mode"]  = mode
        # Affichage parseable par App.html
        print(f"  [Viralité] Score : {result['score']}/100")
        for ax in result.get("axes", []):
            print(f"    {ax['name']:12s}: {ax['score']}")
        print(f"  {VIRALITE_MARKER_START}")
        print(json.dumps(result, ensure_ascii=False))
        print(f"  {VIRALITE_MARKER_END}")
    except Exception as e:
        print(f"  [Viralité] Erreur API : {e}")


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
    print("  ViraCut v9 -- LesCrados.Ai  [DIALOGUE CUT ENGINE]")
    print("=" * 60)
    print(f"  Clips recus        : {len(clips_raw)}")
    print(f"  Dialogue cut       : {cfg(opts,'dialogue_cut')}")
    print(f"  Bruit seuil        : {cfg(opts,'dialogue_noise_db')} dBFS")
    print(f"  Pause min          : {cfg(opts,'dialogue_min_pause')}s")
    print(f"  Tolerance snap     : +/-{cfg(opts,'dialogue_tolerance')}s")
    print(f"  Snap IN            : {cfg(opts,'dialogue_in_snap')}")
    print(f"  xfade [{cfg(opts,'dialogue_xfade_min')}-"
          f"{cfg(opts,'dialogue_xfade_max')}]s adaptatif")

    # Decodage des clips
    raw_paths = []
    for i, v in enumerate(clips_raw):
        p = f"_raw_{i}.mp4"
        with open(p, "wb") as f:
            f.write(base64.b64decode(v["data"]))
        d = duration(p)
        print(f"  Clip {i} : {d:.2f}s  audio={has_audio(p)}")
        raw_paths.append(p)

    # ── Appliquer l'ordre optimal recommandé par l'analyse viralité ──
    clip_order = opts.get("clip_order")
    if not clip_order:
        # Chercher dans pa.json si disponible
        if os.path.exists("pa.json"):
            try:
                with open("pa.json") as _f:
                    _pa = json.load(_f)
                rc = _pa.get("options", {}).get("recommended_config", {})
                clip_order = rc.get("clip_order")
            except Exception:
                pass
    if clip_order and isinstance(clip_order, list) and len(clip_order) == len(raw_paths):
        # Valider les indices
        if sorted(clip_order) == list(range(len(raw_paths))):
            raw_paths  = [raw_paths[i]  for i in clip_order]
            clips_raw  = [clips_raw[i]  for i in clip_order]
            print(f"  Ordre viralité appliqué : {clip_order}")
        else:
            print(f"  Ordre viralité ignoré (indices invalides) : {clip_order}")
    else:
        print(f"  Ordre clips : séquentiel (pas de recommandation viralité)")

    n        = len(raw_paths)
    target   = min(cfg(opts, "cinema_dur"), 13)  # cap TikTok 13s max
    xf_b     = cfg(opts, "cinema_xfade")
    clip_dur = max((target - xf_b * (n - 1)) / n, MIN_CLIP_DUR)
    print(f"\n  Duree cible/segment : {clip_dur:.2f}s  |  xfade base : {xf_b}s\n")

    # ── Analyse viralité avant rendu ───────────────────────────────
    viralite_analysis(clips_raw, opts, raw_paths)

    # Rendu des segments
    segments = []
    for i, src in enumerate(raw_paths):
        out = f"_cin_{i}.mp4"
        print(f"{'─'*55}")
        print(f"  [Segment {i+1}/{n}]")
        seg = build_cinema_segment(src, out, clip_dur,
                                   cfg(opts, "cinema_kb_zoom"), opts)
        segments.append(seg)

    print(f"\n{'─'*55}")
    print("  [Assemblage xfade adaptatif]")
    assemble_cinema(segments, opts)

    print("\n  [Overlay cinema + Logo splash]")
    build_cinema_overlay_no_text(opts)

    size = os.path.getsize("output.mp4") / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"  OK  output.mp4   {size:.1f} MB")
    print(f"{'='*60}")


if __name__ == "__main__":
    start()
