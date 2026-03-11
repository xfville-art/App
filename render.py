"""
render.py — ViraCut Studio v7  ★ LesCrados.Ai Edition ★
═══════════════════════════════════════════════════════
CHANGELOG v7 :
  ★ API → Anthropic (claude-haiku) — plus besoin de GEMINI_API_KEY
  ★ Logo outro 5s animé phase par phase (LES fade / CRADOS slide / .Ai slide)
  ★ Vignette 4 coins pour effet cinéma Hollywood
  ★ Grading Hollywood renforcé par rôle
  ★ Flash BD colorés (rouge/jaune) entre segments
  ★ Textes repositionnés haut/bas — JAMAIS au centre de l'image
  ★ Accent BD vertical rouge sur boîte CORE
═══════════════════════════════════════════════════════
stdlib uniquement + FFmpeg + Anthropic API
"""
import json, base64, os, subprocess, urllib.request, urllib.error
import time, sys, random, hashlib

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL   = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "mode": "auto", "resolution": "720x1280", "fps": 24, "crf": 18,
    "audio_br": 192, "fade_dur": 0.3, "ai_text": True,
    "custom_hook": "", "custom_punch": "",
    "hook_dur": 2.0, "core_dur": 2.5, "punch_dur": 3.0,
    "tolerance": 0.7, "flash_cut": True, "zoom_punch": True,
    "zoom_scale": 1.08, "auto_order": True, "scdet_thr": 10,
    "hook_size": 88, "punch_size": 64, "text_bg": False,
    "cinema_dur": 26, "cinema_clip_min": 7, "cinema_clip_max": 12,
    "cinema_xfade": 0.8, "cinema_kb_zoom": 1.10, "cinema_lb_h": 80,
}


# ═══════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════
def cfg(opts, key):
    return opts.get(key, DEFAULTS[key])


def run(cmd, check=True):
    print(f"    $ {cmd[:115]}{'...' if len(cmd)>115 else ''}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("STDERR:", r.stderr[-800:])
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


def strip_emojis(text):
    return ''.join(c for c in text if ord(c) < 128).strip()


def escape_ffmpeg(text):
    text = strip_emojis(text)
    return (text
            .replace("\\", "\\\\")
            .replace("'",  "\\'")
            .replace(":",  "\\:")
            .replace("%",  "\\%"))


# ═══════════════════════════════════════════════════════════════════════
# ANTHROPIC API
# ═══════════════════════════════════════════════════════════════════════
def anthropic_call(messages, system="", max_tokens=400):
    """Appel Anthropic /v1/messages. Retourne le texte ou None."""
    if not ANTHROPIC_KEY:
        print("    [API] ANTHROPIC_API_KEY absent")
        return None

    payload = {"model": ANTHROPIC_MODEL, "max_tokens": max_tokens, "messages": messages}
    if system:
        payload["system"] = system

    for attempt in range(2):
        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
                return data["content"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"    [API] HTTP {e.code}: {body}")
            if e.code in (400, 401, 403):
                return None
        except Exception as e:
            print(f"    [API] Erreur: {e}")
        if attempt == 0:
            print("    [API] Retry dans 3s...")
            time.sleep(3)
    return None


def test_api():
    if not ANTHROPIC_KEY:
        print("  API     : ANTHROPIC_API_KEY absent")
        return False
    result = anthropic_call([{"role": "user", "content": "Dis juste OK"}],
                            max_tokens=10)
    if result and "OK" in result.upper():
        print(f"  API     : OK {ANTHROPIC_MODEL} operationnel")
        return True
    print(f"  API     : reponse: {result}")
    return bool(result)


# ═══════════════════════════════════════════════════════════════════════
# FALLBACK BANK
# ═══════════════════════════════════════════════════════════════════════
FALLBACK_BANK = [
    {"hook": "CA SENT MAUVAIS",  "core": "et pourtant il recommence",            "punch": "la prochaine carte sera pire"},
    {"hook": "REGARDE CA",       "core": "personne ne peut expliquer ca",         "punch": "on a quand meme fait une carte"},
    {"hook": "C EST INTERDIT",   "core": "mais les Crados s en fichent",          "punch": "carte disponible maintenant"},
    {"hook": "POURQUOI LUI",     "core": "la question que tout le monde se pose", "punch": "la reponse est dans la carte"},
    {"hook": "ENCORE LUI",       "core": "le pire personnage de la collection",   "punch": "et pourtant tu veux la carte"},
    {"hook": "NON MAIS",         "core": "ca depasse vraiment les bornes",        "punch": "on en a fait une carte quand meme"},
    {"hook": "TROP CRADO",       "core": "meme pour les Crados c est trop",       "punch": "la carte existe deja desolee"},
    {"hook": "T AS VU CA",       "core": "incroyable mais bien reel",             "punch": "ta collection est incomplete"},
    {"hook": "LE PLUS BIZARRE",  "core": "de toute la collection Crados",         "punch": "et tu veux quand meme la carte"},
    {"hook": "IMPOSSIBLE",       "core": "enfin presque selon les Crados",        "punch": "une carte pour prouver que si"},
]


def pick_fallback(seed_path=""):
    if seed_path:
        h = int(hashlib.md5(seed_path.encode()).hexdigest(), 16)
        return FALLBACK_BANK[h % len(FALLBACK_BANK)]
    return random.choice(FALLBACK_BANK)


# ═══════════════════════════════════════════════════════════════════════
# VISION + TEXTES (Anthropic)
# ═══════════════════════════════════════════════════════════════════════
def extract_frame(path, t_ratio, out):
    dur = duration(path)
    t   = max(0.0, dur * t_ratio)
    subprocess.run(
        f'ffmpeg -y -ss {t:.2f} -i "{path}" -vframes 1 -q:v 3 "{out}" 2>/dev/null',
        shell=True
    )
    return os.path.isfile(out)


def vision_describe(path, role):
    """3 frames -> Claude Vision -> description FR precise."""
    frames_b64 = []
    for ratio in [0.10, 0.50, 0.85]:
        frame_out = f"_frame_{role}_{int(ratio*100)}.jpg"
        if extract_frame(path, ratio, frame_out):
            with open(frame_out, "rb") as f:
                frames_b64.append(base64.b64encode(f.read()).decode())

    if not frames_b64:
        return ""

    content = []
    for b64 in frames_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
        })
    content.append({
        "type": "text",
        "text": (
            f"Ces images viennent d'un clip video (role: {role}) pour Les Crados TikTok.\n"
            "Decris EN FRANCAIS en 2-3 phrases TRES courtes et precises :\n"
            "1. Qui est la (personnage, aspect physique notable)\n"
            "2. L'action principale (ce qui est bizarre, drole, degoutant)\n"
            "3. L'element le plus WTF/choquant visuellement\n"
            "Sois factuel et ultra-specifique sur ce que tu VOIS reellement."
        )
    })

    print(f"    [VISION] Analyse clip {role}...")
    result = anthropic_call(
        [{"role": "user", "content": content}],
        system="Tu analyses des clips video pour Les Crados TikTok. Style direct, factuel.",
        max_tokens=250
    )
    if result:
        print(f"    [VISION] {role}: {result[:100]}...")
        return result
    return ""


def generate_texts(descriptions, opts):
    """Hook + core + punchline via Anthropic."""
    desc_lines = "\n".join(
        f"[{r.upper()}] {d}" for r, d in descriptions.items() if d
    ).strip()

    if not desc_lines:
        return None

    custom_hook  = (opts or {}).get("custom_hook", "").strip()
    custom_punch = (opts or {}).get("custom_punch", "").strip()
    hook_inst    = f'Hook OBLIGATOIRE exactement : "{custom_hook}"' if custom_hook else "Genere le hook."
    punch_inst   = f'Punchline OBLIGATOIRE exactement : "{custom_punch}"' if custom_punch else "Genere la punchline."

    prompt = (
        "Tu es redacteur creatif de Les Crados (TikTok FR, style Garbage Pail Kids).\n"
        "Humour absurde, crado, choquant, ironique. Zero censure.\n\n"
        f"CLIPS analyses par IA vision :\n{desc_lines}\n\n"
        "REGLES :\n"
        "- Textes SPECIFIQUES au contenu reel, jamais generiques\n"
        "- Aucun emoji, aucun accent, aucun caractere special (FFmpeg)\n"
        "- HOOK en MAJUSCULES max 4 mots\n"
        "- core en minuscules 5-6 mots humour absurde\n"
        "- punch en minuscules 6-8 mots chute drole et precise\n\n"
        f"{hook_inst}\n{punch_inst}\n\n"
        'Reponds UNIQUEMENT avec ce JSON (pas de markdown) :\n'
        '{"hook":"MOTS CHOC","core":"phrase drole ici","punch":"chute absurde precise"}'
    )

    print("    [TEXTES] Generation Claude...")
    raw = anthropic_call(
        [{"role": "user", "content": prompt}],
        system="Tu generes uniquement du JSON valide, sans markdown, sans texte autour.",
        max_tokens=200
    )
    if not raw:
        return None

    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(raw)
        print(f"    [TEXTES] hook={result.get('hook')} | core={result.get('core')}")
        return result
    except Exception:
        start = raw.find("{"); end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except Exception:
                pass
    print(f"    [TEXTES] Parse JSON echoue: {raw[:200]}")
    return None


# ═══════════════════════════════════════════════════════════════════════
# [1] NORMALISATION
# ═══════════════════════════════════════════════════════════════════════
def normalize(src, out, opts):
    W, H = cfg(opts, "resolution").split("x")
    fps = cfg(opts, "fps"); crf = cfg(opts, "crf"); abr = cfg(opts, "audio_br")
    scale_crop = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps}")
    if has_audio(src):
        cmd = (f'ffmpeg -y -i "{src}" -vf "{scale_crop}" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset ultrafast '
               f'-c:a aac -b:a {abr}k -ar 44100 -ac 2 "{out}"')
    else:
        cmd = (f'ffmpeg -y -i "{src}" -f lavfi -i "anullsrc=r=44100:cl=stereo" '
               f'-filter_complex "[0:v]{scale_crop}[v];[1:a]atrim=0:10[a]" '
               f'-map "[v]" -map "[a]" -c:v libx264 -pix_fmt yuv420p -crf {crf} '
               f'-preset ultrafast -c:a aac -b:a {abr}k -shortest "{out}"')
    run(cmd)


# ═══════════════════════════════════════════════════════════════════════
# [2] METRIQUES
# ═══════════════════════════════════════════════════════════════════════
def extract_metrics(path, scdet_thr=10):
    info = ffprobe(path)
    dur  = float(info.get("format", {}).get("duration", 0))
    rms  = 40.0
    try:
        r = subprocess.run(f'ffmpeg -i "{path}" -af volumedetect -f null /dev/null 2>&1',
                           shell=True, capture_output=True, text=True)
        for line in (r.stdout + r.stderr).split("\n"):
            if "mean_volume" in line:
                rms = float(line.split(":")[-1].strip().split()[0]) + 91
    except Exception:
        pass
    motion = 30.0
    try:
        r = subprocess.run(
            f'ffmpeg -i "{path}" -vf "mpdecimate,metadata=print:file=-" '
            f'-f null /dev/null 2>&1 | grep -c "lavfi.mpdecimate.drop=1" || echo 0',
            shell=True, capture_output=True, text=True)
        dropped = int((r.stdout + r.stderr).strip().split("\n")[0] or "0")
        motion = max(0.0, 60.0 - dropped * 2)
    except Exception:
        pass
    scene_count = 0
    try:
        r = subprocess.run(
            f'ffmpeg -i "{path}" -vf "select=gt(scene\\,{scdet_thr/100:.3f}),showinfo" '
            f'-f null /dev/null 2>&1 | grep -c "n:" || echo 0',
            shell=True, capture_output=True, text=True)
        scene_count = int((r.stdout + r.stderr).strip().split("\n")[0] or "0")
    except Exception:
        pass
    return {"duration": dur, "scene_count": scene_count,
            "density": scene_count / max(dur, 1.0), "rms": rms, "motion": motion}


# ═══════════════════════════════════════════════════════════════════════
# [3] SCORING
# ═══════════════════════════════════════════════════════════════════════
def score_and_order(clips_meta):
    scored = []
    for m in clips_meta:
        d = m["duration"]; dens = m["density"]; mot = m["motion"]; rms = m["rms"]
        early = dens * 2; late = rms / 10.0
        h = early * 12 + m["scene_count"] * 0.5 + mot - d
        c = dens * 8 + mot + d
        p = late * 12 + rms - dens
        scored.append({**m, "hook_score": h, "core_score": c, "punch_score": p})
    n = len(scored)
    if n == 1:
        scored[0]["role"] = "hook"
    elif n == 2:
        by_h = sorted(scored, key=lambda x: x["hook_score"], reverse=True)
        by_h[0]["role"] = "hook"; by_h[1]["role"] = "punch"; scored = by_h
    else:
        by_h = sorted(scored, key=lambda x: x["hook_score"], reverse=True)
        by_h[0]["role"] = "hook"
        rest = sorted(by_h[1:], key=lambda x: x["punch_score"], reverse=True)
        rest[0]["role"] = "punch"
        for r in rest[1:]: r["role"] = "core"
        scored = [by_h[0]] + rest
    order = {"hook": 0, "core": 1, "punch": 2}
    scored.sort(key=lambda x: order.get(x.get("role", "core"), 1))
    return scored


# ═══════════════════════════════════════════════════════════════════════
# [4] CUT NATUREL
# ═══════════════════════════════════════════════════════════════════════
def find_natural_cut(path, target, tolerance, scdet_thr):
    vid_dur = duration(path)
    if vid_dur <= 0:
        return target
    scene_times = []
    try:
        r = subprocess.run(
            f'ffmpeg -i "{path}" -vf "select=gt(scene\\,{scdet_thr/100:.3f}),showinfo" '
            f'-f null /dev/null 2>&1',
            shell=True, capture_output=True, text=True)
        for line in (r.stdout + r.stderr).split("\n"):
            if "pts_time:" in line:
                for part in line.split():
                    if part.startswith("pts_time:"):
                        try: scene_times.append(float(part.split(":", 1)[1]))
                        except Exception: pass
    except Exception:
        pass
    candidates = [t for t in scene_times
                  if target - tolerance <= t <= target + tolerance and t > 0]
    return min(candidates, key=lambda t: abs(t - target)) if candidates else min(target, vid_dur)


# ═══════════════════════════════════════════════════════════════════════
# LOGO SPLASH ANIME — LesCrados.Ai (5 secondes)
# ═══════════════════════════════════════════════════════════════════════
def build_logo_splash(out, opts):
    """
    Sequence outro Hollywood 5s — animations phasees (FFmpeg-safe).
    Strategie : on genere 4 segments independants et on les fusionne
    pour eviter les alpha dynamiques non supportes dans drawbox/drawtext.

    Phase 1 : 0.0-0.8s  — fond noir + 'LES' argent (fade in global)
    Phase 2 : 0.8-1.45s — + 'CRADOS' slide depuis le bas
    Phase 3 : 1.45-1.7s — + ligne rouge pop
    Phase 4 : 1.7-4.2s  — + '.Ai' slide depuis le bas, hold
    Phase 5 : 4.2-5.0s  — fade out global vers noir

    Toutes les expressions y='...' dans drawtext sont supportees.
    Aucun alpha dynamique dans drawbox ou drawtext (FFmpeg 4.x-safe).
    """
    W, H  = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps")
    crf   = cfg(opts, "crf")
    Wi, Hi = int(W), int(H)
    dur   = 5.0

    # Tailles police — calibrees pour ne pas depasser Wi=720px
    # Liberation Bold : ratio reel ~0.78 par char
    # CRADOS (6 chars) : 142px * 0.78 * 6 + 2*12(border) = 664 + 24 = 688 => marge ok
    les_sz    = 78
    crados_sz = 142
    ai_sz     = 82

    # Positions verticales — bloc centre
    total_h   = les_sz + 18 + crados_sz + 14 + ai_sz
    block_top = (Hi - total_h) // 2
    les_y     = block_top
    crados_y  = les_y + les_sz + 18
    deco_y    = crados_y + crados_sz + 6
    ai_y      = deco_y + 16

    # Timings phases (fixes)
    t_les  = 0.3
    t_crad = 0.8;  d_crad = 0.50
    t_deco = 1.45
    t_ai   = 1.7;  d_ai   = 0.40
    t_fout = 4.2;  d_fout = 0.80

    # ── Slide CRADOS depuis le bas (y expression — supporte) ──────────
    # y part de Hi (hors ecran) et arrive a crados_y en d_crad secondes
    crad_y_expr = (
        f"if(lt(t,{t_crad}),{Hi},"
        f"if(lt(t-{t_crad},{d_crad}),"
        f"{Hi}+({crados_y}-{Hi})*((t-{t_crad})/{d_crad}),"
        f"{crados_y}))"
    )

    # ── Slide .Ai depuis le bas ────────────────────────────────────────
    ai_y_expr = (
        f"if(lt(t,{t_ai}),{Hi},"
        f"if(lt(t-{t_ai},{d_ai}),"
        f"{Hi}+({ai_y}-{Hi})*((t-{t_ai})/{d_ai}),"
        f"{ai_y}))"
    )

    # ── Fades globaux video (fade filter — toujours supporte) ─────────
    fade_in  = f"fade=t=in:st=0:d=0.5:color=black"
    fade_out = f"fade=t=out:st={t_fout}:d={d_fout}:color=black"

    # ── Drawtext/drawbox — NO alpha dynamique, uniquement enable= ─────

    # LES : apparait a t_les, statique (pas d'alpha dynamique)
    dt_les_sh = (
        f"drawtext=fontfile={FONT}:text='LES':"
        f"fontsize={les_sz}:fontcolor=#444444:borderw=0:"
        f"x=(w-text_w)/2+5:y={les_y + 6}:"
        f"enable='gte(t,{t_les})'"
    )
    dt_les = (
        f"drawtext=fontfile={FONT}:text='LES':"
        f"fontsize={les_sz}:fontcolor=#C8C8C8:borderw=4:bordercolor=#555555:"
        f"x=(w-text_w)/2:y={les_y}:"
        f"enable='gte(t,{t_les})'"
    )

    # CRADOS — triple couche chrome, borderw reduits pour rester dans 720px
    dt_crad_glow = (
        f"drawtext=fontfile={FONT}:text='CRADOS':"
        f"fontsize={crados_sz}:fontcolor=#222222:borderw=12:bordercolor=#111111:"
        f"x=(w-text_w)/2:y='{crad_y_expr}':"
        f"enable='gte(t,{t_crad})'"
    )
    dt_crad_mid = (
        f"drawtext=fontfile={FONT}:text='CRADOS':"
        f"fontsize={crados_sz}:fontcolor=#777777:borderw=5:bordercolor=#333333:"
        f"x=(w-text_w)/2:y='{crad_y_expr}':"
        f"enable='gte(t,{t_crad})'"
    )
    dt_crad = (
        f"drawtext=fontfile={FONT}:text='CRADOS':"
        f"fontsize={crados_sz}:fontcolor=white:borderw=2:bordercolor=#AAAAAA:"
        f"x=(w-text_w)/2:y='{crad_y_expr}':"
        f"enable='gte(t,{t_crad})'"
    )

    # Ligne rouge decorative — alpha STATIQUE (pas d'expression)
    deco_x  = Wi // 4
    deco_w  = Wi // 2
    dt_deco = (
        f"drawbox=x={deco_x}:y={deco_y}:w={deco_w}:h=5:"
        f"color=#FF2442@0.92:t=fill:"
        f"enable='gte(t,{t_deco})'"
    )

    # .Ai rouge — slide depuis le bas (y expr OK), shadow puis couleur
    dt_ai_sh = (
        f"drawtext=fontfile={FONT}:text='.Ai':"
        f"fontsize={ai_sz}:fontcolor=#550011:borderw=0:"
        f"x=(w-text_w)/2+5:y='{ai_y_expr}':"
        f"enable='gte(t,{t_ai})'"
    )
    dt_ai = (
        f"drawtext=fontfile={FONT}:text='.Ai':"
        f"fontsize={ai_sz}:fontcolor=#FF2442:borderw=6:bordercolor=#770011:"
        f"x=(w-text_w)/2:y='{ai_y_expr}':"
        f"enable='gte(t,{t_ai})'"
    )

    # Sous-texte discret — statique, alpha fixe dans la couleur
    dt_sub = (
        f"drawtext=fontfile={FONT}:text='lescrados.ai':"
        f"fontsize=22:fontcolor=white@0.22:borderw=0:"
        f"x=(w-text_w)/2:y={Hi - 90}:"
        f"enable='gte(t,2.5)'"
    )

    vf = ",".join([
        dt_les_sh, dt_les,
        dt_crad_glow, dt_crad_mid, dt_crad,
        dt_deco,
        dt_ai_sh, dt_ai,
        dt_sub,
        fade_in, fade_out,
    ])

    run(f'ffmpeg -y '
        f'-f lavfi -i "color=c=black:size={W}x{H}:rate={fps}" '
        f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
        f'-t {dur} '
        f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{dur}[a]" '
        f'-map "[v]" -map "[a]" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a 128k "{out}"')


def append_logo(premain, opts):
    """Concatene premain + logo splash 5s -> output.mp4."""
    crf = cfg(opts, "crf"); abr = cfg(opts, "audio_br")
    print("  [LOGO] Build LesCrados.Ai splash 5s anime...")
    build_logo_splash("_logo.mp4", opts)
    with open("_concat_logo.txt", "w") as f:
        f.write(f"file '{premain}'\n")
        f.write("file '_logo.mp4'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i _concat_logo.txt '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k output.mp4')
    print("  [LOGO] Logo splash 5s ajoute")


# ═══════════════════════════════════════════════════════════════════════
# MODE PUNCH
# ═══════════════════════════════════════════════════════════════════════
def build_punch_segment(src, out, cut_dur, role, opts):
    W, H  = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps"); crf = cfg(opts, "crf"); abr = cfg(opts, "audio_br")

    # Grading Hollywood renforce par role
    if role == "hook":
        grade = "eq=saturation=1.65:brightness=0.06:contrast=1.22,hue=h=6"
    elif role == "core":
        grade = "eq=saturation=1.12:brightness=-0.02:contrast=1.10"
    else:
        grade = "eq=saturation=0.60:brightness=-0.07:contrast=1.25,hue=h=-12"

    zoom_filter = ""
    if role == "core" and cfg(opts, "zoom_punch"):
        zs  = cfg(opts, "zoom_scale")
        inc = (zs - 1.0) / max(cut_dur * fps, 1)
        zoom_filter = (
            f",zoompan=z='min(zoom+{inc:.6f},{zs})'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}:fps={fps}"
        )

    scale_crop = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps}")
    vf = f"{scale_crop},{grade}{zoom_filter}"

    if has_audio(src):
        cmd = (f'ffmpeg -y -ss 0 -t {cut_dur:.3f} -i "{src}" -vf "{vf}" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
               f'-c:a aac -b:a {abr}k -ar 44100 -ac 2 -shortest "{out}"')
    else:
        cmd = (f'ffmpeg -y -ss 0 -t {cut_dur:.3f} -i "{src}" '
               f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
               f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{cut_dur:.3f}[a]" '
               f'-map "[v]" -map "[a]" -c:v libx264 -pix_fmt yuv420p -crf {crf} '
               f'-preset fast -c:a aac -b:a {abr}k -shortest "{out}"')
    run(cmd)


def build_flash(out, opts, hex_color="0xFFFFFF"):
    W, H = cfg(opts, "resolution").split("x"); fps = cfg(opts, "fps")
    dur  = round(1.0 / fps, 6)
    color = hex_color if hex_color.startswith("0x") else f"0x{hex_color.lstrip('#')}"
    run(f'ffmpeg -y '
        f'-f lavfi -i "color=c={color}:size={W}x{H}:rate={fps}" '
        f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
        f'-t {dur} -c:v libx264 -pix_fmt yuv420p -crf 18 -preset ultrafast '
        f'-c:a aac -b:a 128k "{out}"')
    return dur


def build_punch_final(segments, texts, opts):
    """
    Assemble segments + flash BD colores + textes animes style BD.
    HOOK  -> barre HAUT (fond rouge), slide depuis le haut
    CORE  -> 72% hauteur, boite sombre + accent vertical rouge
    PUNCH -> barre BAS (fond orange), slide depuis le bas
    Puis concat logo LesCrados.Ai 5s.
    """
    W, H  = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps"); crf = cfg(opts, "crf"); abr = cfg(opts, "audio_br")
    fade  = cfg(opts, "fade_dur")
    Wi, Hi = int(W), int(H)

    hook_sz  = cfg(opts, "hook_size")
    punch_sz = cfg(opts, "punch_size")
    core_sz  = int(hook_sz * 0.80)

    hook_txt  = escape_ffmpeg(texts.get("hook",  "TAS VU CA"))
    core_txt  = escape_ffmpeg(texts.get("core",  "incroyable mais vrai"))
    punch_txt = escape_ffmpeg(texts.get("punch", "une carte a collectionner"))

    # Flash BD colores
    flash_dur = 0.0; flash_paths = []
    if cfg(opts, "flash_cut"):
        flash_colors = ["0xFF2442", "0xFFD60A", "0xFF2442"]
        for i in range(len(segments) - 1):
            fp = f"_flash_{i}.mp4"
            flash_dur = build_flash(fp, opts, flash_colors[i % len(flash_colors)])
            flash_paths.append(fp)

    # concat.txt
    with open("concat.txt", "w") as f:
        for i, (path, role, _dur) in enumerate(segments):
            f.write(f"file '{path}'\n")
            if i < len(segments) - 1 and flash_paths:
                f.write(f"file '{flash_paths[i]}'\n")

    run("ffmpeg -y -f concat -safe 0 -i concat.txt -c copy _base.mp4")

    # Timings
    t_map = {}; t = 0.0
    for i, (path, role, dur) in enumerate(segments):
        if role not in t_map: t_map[role] = (t, t + dur)
        t += dur
        if i < len(segments) - 1 and flash_paths: t += flash_dur
    total = t

    h_s, h_e = t_map.get("hook",  (0.0, 2.0))
    c_s, c_e = t_map.get("core",  (h_e, h_e + 2.5))
    p_s, p_e = t_map.get("punch", (c_e, total))

    # Layout — lb_top adaptatif : assez grand pour contenir le texte hook
    # + marges internes (8px haut et bas)
    lb_top = hook_sz + 16        # ex: 88+16 = 104px
    lb_bot = punch_sz + 16       # ex: 64+16 = 80px
    lb_y_b = Hi - lb_bot

    # Animations
    hook_adur  = 0.20
    hook_y_fin = lb_top // 2 - hook_sz // 2   # centre dans la barre
    # Pas de max(6,...) — lb_top est maintenant toujours >= hook_sz + 16
    slide_up_y = (
        f"if(lt(t-{h_s:.3f},{hook_adur}),"
        f"-{hook_sz}+(t-{h_s:.3f})/{hook_adur}*({hook_y_fin}+{hook_sz}),"
        f"{hook_y_fin})"
    )

    core_y = int(Hi * 0.72)
    core_alpha = (
        f"if(lt(t-{c_s:.3f},0.15),(t-{c_s:.3f})/0.15,1)"
    )

    punch_y_fin = lb_y_b + lb_bot // 2 - punch_sz // 2
    slide_dn_y  = (
        f"if(lt(t-{p_s:.3f},0.20),"
        f"h-{punch_sz}+(h-{punch_y_fin})*(1-(t-{p_s:.3f})/0.20),"
        f"{punch_y_fin})"
    )

    # Letterbox permanent
    lb = (f"drawbox=x=0:y=0:w={W}:h={lb_top}:color=black@0.95:t=fill,"
          f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_bot}:color=black@0.95:t=fill")

    # Vignette 4 coins
    vw = Wi // 5; vh = Hi // 6
    vignette = (
        f"drawbox=x=0:y=0:w={vw}:h={vh}:color=black@0.35:t=fill,"
        f"drawbox=x={Wi-vw}:y=0:w={vw}:h={vh}:color=black@0.35:t=fill,"
        f"drawbox=x=0:y={Hi-vh}:w={vw}:h={vh}:color=black@0.35:t=fill,"
        f"drawbox=x={Wi-vw}:y={Hi-vh}:w={vw}:h={vh}:color=black@0.35:t=fill"
    )

    # HOOK — fond rouge + texte blanc/jaune
    dt_hook_box = (
        f"drawbox=x=0:y=0:w={W}:h={lb_top}:color=0xFF2442@0.88:t=fill:"
        f"enable='between(t,{h_s:.3f},{h_e:.3f})'"
    )
    dt_hook_sh  = (
        f"drawtext=fontfile={FONT}:text='{hook_txt}':"
        f"fontsize={hook_sz}:fontcolor=#880011:borderw=0:"
        f"x=(w-text_w)/2+3:y={hook_y_fin + 4}:"
        f"enable='between(t,{h_s:.3f},{h_e:.3f})'"
    )
    dt_hook = (
        f"drawtext=fontfile={FONT}:text='{hook_txt}':"
        f"fontsize={hook_sz}:fontcolor=white:borderw=8:bordercolor=#FFD60A:"
        f"x=(w-text_w)/2:y='{slide_up_y}':"
        f"enable='between(t,{h_s:.3f},{h_e:.3f})'"
    )

    # CORE — boite sombre 72% + accent rouge
    bx_h = core_sz + 22; bx_y = core_y - core_sz - 10
    dt_core_box = (
        f"drawbox=x=0:y={bx_y}:w={W}:h={bx_h}:color=black@0.75:t=fill:"
        f"enable='between(t,{c_s:.3f},{c_e:.3f})'"
    )
    dt_core_acc = (
        f"drawbox=x=0:y={bx_y}:w=8:h={bx_h}:color=0xFF2442@0.95:t=fill:"
        f"enable='between(t,{c_s:.3f},{c_e:.3f})'"
    )
    dt_core = (
        f"drawtext=fontfile={FONT}:text='{core_txt}':"
        f"fontsize={core_sz}:fontcolor=white:borderw=4:bordercolor=#FF2442:"
        f"x=(w-text_w)/2:y={core_y - core_sz}:"
        f"alpha='{core_alpha}':"
        f"enable='between(t,{c_s:.3f},{c_e:.3f})'"
    )

    # PUNCH — fond orange + texte blanc
    dt_punch_box = (
        f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_bot}:color=0xFF6B00@0.95:t=fill:"
        f"enable='between(t,{p_s:.3f},{p_e:.3f})'"
    )
    dt_punch = (
        f"drawtext=fontfile={FONT}:text='{punch_txt}':"
        f"fontsize={punch_sz}:fontcolor=white:borderw=5:bordercolor=#882200:"
        f"x=(w-text_w)/2:y='{slide_dn_y}':"
        f"enable='between(t,{p_s:.3f},{p_e:.3f})'"
    )

    # Watermark discret
    wm = (f"drawtext=fontfile={FONT}:text='LesCrados.Ai':"
          f"fontsize=19:fontcolor=white@0.25:borderw=0:"
          f"x=w-text_w-12:y={lb_y_b + lb_bot // 2 - 9}")

    vf = ",".join([
        lb, vignette,
        dt_hook_box, dt_hook_sh, dt_hook,
        dt_core_box, dt_core_acc, dt_core,
        dt_punch_box, dt_punch,
        wm,
    ])
    af = f"afade=t=out:st={max(0.0, total - fade):.3f}:d={fade}"

    run(f'ffmpeg -y -i _base.mp4 -vf "{vf}" -af "{af}" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k _premain.mp4')

    append_logo("_premain.mp4", opts)


# ═══════════════════════════════════════════════════════════════════════
# MODE CINEMA
# ═══════════════════════════════════════════════════════════════════════
def build_cinema_segment(src, seg_out, clip_dur, kb_zoom, opts):
    W, H  = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps"); crf = cfg(opts, "crf"); abr = cfg(opts, "audio_br")
    scale_crop = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps}")
    grade  = "eq=saturation=0.88:brightness=-0.04:contrast=1.18"
    frames = clip_dur * fps; inc = (kb_zoom - 1.0) / max(frames, 1)
    kb_z   = f"min(zoom+{inc:.6f},{kb_zoom})"
    kb_filter = (f"zoompan=z='{kb_z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                 f":d=1:s={W}x{H}:fps={fps}")
    vf = f"{scale_crop},{grade},{kb_filter}"

    if has_audio(src):
        cmd = (f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -vf "{vf}" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
               f'-c:a aac -b:a {abr}k -ar 44100 -ac 2 -shortest "{seg_out}"')
    else:
        cmd = (f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" '
               f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
               f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{clip_dur:.2f}[a]" '
               f'-map "[v]" -map "[a]" -c:v libx264 -pix_fmt yuv420p -crf {crf} '
               f'-preset fast -c:a aac -b:a {abr}k -shortest "{seg_out}"')
    run(cmd)


def assemble_cinema(seg_paths, xfade_dur, opts):
    crf = cfg(opts, "crf"); abr = cfg(opts, "audio_br")
    n   = len(seg_paths)
    if n == 1:
        import shutil; shutil.copy(seg_paths[0], "_assembled.mp4"); return

    inputs = " ".join(f'-i "{p}"' for p in seg_paths)
    durs   = [duration(p) for p in seg_paths]
    v_parts = []; a_parts = []
    offset = durs[0] - xfade_dur; prev_v = "[0:v]"; prev_a = "[0:a]"

    for i in range(1, n):
        nv = f"[xv{i}]" if i < n - 1 else "[vfin]"
        na = f"[xa{i}]" if i < n - 1 else "[afin]"
        v_parts.append(f"{prev_v}[{i}:v]xfade=transition=fade"
                       f":duration={xfade_dur:.2f}:offset={offset:.3f}{nv}")
        a_parts.append(f"{prev_a}[{i}:a]acrossfade=d={xfade_dur:.2f}:c1=tri:c2=tri{na}")
        prev_v = nv; prev_a = na; offset += durs[i] - xfade_dur

    fc = ";".join(v_parts + a_parts)
    run(f'ffmpeg -y {inputs} -filter_complex "{fc}" '
        f'-map "[vfin]" -map "[afin]" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k _assembled.mp4')


def build_cinema_overlay(texts, opts):
    W, H   = cfg(opts, "resolution").split("x")
    lb_h   = cfg(opts, "cinema_lb_h")
    crf    = cfg(opts, "crf"); abr = cfg(opts, "audio_br"); fade = cfg(opts, "fade_dur")
    Wi, Hi = int(W), int(H)

    lb_top = hook_sz + 16    # adaptatif : 54+16=70px
    lb_bot = punch_sz + 16   # adaptatif : 46+16=62px
    lb_y_b = Hi - lb_bot
    total  = duration("_assembled.mp4")

    h_e   = total * 0.20
    mid_s = total * 0.20; mid_e = total * 0.72
    fin_s = total * 0.72

    hook_txt  = escape_ffmpeg(texts.get("hook",  "LES CRADOS"))
    core_txt  = escape_ffmpeg(texts.get("core",  "incroyable mais vrai"))
    punch_txt = escape_ffmpeg(texts.get("punch", "une carte a collectionner"))

    hook_sz  = 54; core_sz = 48; punch_sz = 46
    core_y   = int(Hi * 0.72)
    hook_y   = lb_top // 2 - hook_sz // 2    # centre dans barre du haut
    punch_y  = lb_y_b + lb_bot // 2 - punch_sz // 2

    # Letterbox permanent
    lb = (f"drawbox=x=0:y=0:w={W}:h={lb_top}:color=black@0.95:t=fill,"
          f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_bot}:color=black@0.95:t=fill")

    # Vignette
    vw = Wi // 5; vh = Hi // 6
    vignette = (
        f"drawbox=x=0:y=0:w={vw}:h={vh}:color=black@0.35:t=fill,"
        f"drawbox=x={Wi-vw}:y=0:w={vw}:h={vh}:color=black@0.35:t=fill,"
        f"drawbox=x=0:y={Hi-vh}:w={vw}:h={vh}:color=black@0.35:t=fill,"
        f"drawbox=x={Wi-vw}:y={Hi-vh}:w={vw}:h={vh}:color=black@0.35:t=fill"
    )

    _hd = hook_txt if hook_txt not in ('LES CRADOS', 'LES\\ CRADOS') else ''
    dt_hook_bg = (f"drawbox=x=0:y=0:w={W}:h={lb_top}:color=0xFF2442@0.88:t=fill:"
                  f"enable='between(t,0,{h_e:.2f})'")
    dt_hook = (
        f"drawtext=fontfile={FONT}:text='{_hd}':"
        f"fontsize={hook_sz}:fontcolor=white:borderw=7:bordercolor=#FFD60A:"
        f"x=(w-text_w)/2:y={hook_y}:"
        f"enable='between(t,0,{h_e:.2f})'"
    ) if _hd else ""

    bx_h = core_sz + 22; bx_y = core_y - core_sz - 10
    box_core  = (f"drawbox=x=0:y={bx_y}:w={W}:h={bx_h}:color=black@0.75:t=fill:"
                 f"enable='between(t,{mid_s:.2f},{mid_e:.2f})'")
    core_acc  = (f"drawbox=x=0:y={bx_y}:w=8:h={bx_h}:color=0xFF2442@0.95:t=fill:"
                 f"enable='between(t,{mid_s:.2f},{mid_e:.2f})'")
    sub       = (f"drawtext=fontfile={FONT}:text='{core_txt}':"
                 f"fontsize={core_sz}:fontcolor=white:borderw=4:bordercolor=#FF2442:"
                 f"x=(w-text_w)/2:y={core_y - core_sz}:"
                 f"enable='between(t,{mid_s:.2f},{mid_e:.2f})'")

    punch_box = (f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_bot}:color=0xFF6B00@0.95:t=fill:"
                 f"enable='between(t,{fin_s:.2f},{total:.2f})'")
    punch     = (f"drawtext=fontfile={FONT}:text='{punch_txt}':"
                 f"fontsize={punch_sz}:fontcolor=white:borderw=5:bordercolor=#882200:"
                 f"x=(w-text_w)/2:y={punch_y}:"
                 f"enable='between(t,{fin_s:.2f},{total:.2f})'")

    wm = (f"drawtext=fontfile={FONT}:text='LesCrados.Ai':"
          f"fontsize=19:fontcolor=white@0.25:borderw=0:"
          f"x=w-text_w-12:y={lb_y_b + lb_bot // 2 - 9}")

    parts = [lb, vignette, dt_hook_bg] + ([dt_hook] if dt_hook else []) + \
            [box_core, core_acc, sub, punch_box, punch, wm]
    vf = ",".join(p for p in parts if p)
    af = f"afade=t=out:st={max(0.0, total - fade):.3f}:d={fade}"

    run(f'ffmpeg -y -i _assembled.mp4 -vf "{vf}" -af "{af}" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k _premain.mp4')

    append_logo("_premain.mp4", opts)


# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════
def start():
    if not os.path.exists("p.json"):
        print("p.json manquant"); sys.exit(1)

    with open("p.json") as f:
        data = json.load(f)

    clips_raw = data.get("videos", [])
    opts      = data.get("options", {})
    mode      = cfg(opts, "mode")

    print("=" * 56)
    print("  ViraCut render.py v7 -- LesCrados.Ai Edition")
    print(f"  Mode : {mode}  |  Clips : {len(clips_raw)}")
    test_api()
    print("=" * 56)

    if not clips_raw:
        print("Aucun clip recu"); sys.exit(1)

    raw_paths = []
    for i, v in enumerate(clips_raw):
        raw = f"_raw_{i}.mp4"
        with open(raw, "wb") as f:
            f.write(base64.b64decode(v["data"]))
        raw_paths.append((raw, v.get("role", "auto")))
        print(f"  Clip {i}: role={v.get('role','auto')}")

    if mode == "auto":
        total_dur = sum(duration(p) for p, _ in raw_paths)
        mode = "cinema" if (len(raw_paths) == 1 or total_dur > 12.0) else "punch"
        print(f"\n  Mode AUTO -> {mode.upper()} (duree: {total_dur:.1f}s)")

    # ── MODE CINEMA ──────────────────────────────────────────────────
    if mode == "cinema":
        n        = len(raw_paths)
        target   = cfg(opts, "cinema_dur")
        cmin     = cfg(opts, "cinema_clip_min")
        cmax     = cfg(opts, "cinema_clip_max")
        xfade    = cfg(opts, "cinema_xfade")
        kb_zoom  = cfg(opts, "cinema_kb_zoom")
        clip_dur = min(cmax, max(cmin, (target - xfade * (n - 1)) / n))

        print(f"\n[1/5] Segments Ken Burns Hollywood ({n}x{clip_dur:.1f}s)...")
        seg_paths = []
        for i, (src, role) in enumerate(raw_paths):
            seg_out = f"_cin_{i}.mp4"
            build_cinema_segment(src, seg_out, clip_dur, kb_zoom, opts)
            seg_paths.append(seg_out)

        print("\n[2/5] Vision IA + descriptions...")
        descriptions = {}
        if ANTHROPIC_KEY and cfg(opts, "ai_text"):
            for i, (src, role) in enumerate(raw_paths):
                lbl  = role if role != "auto" else f"clip{i}"
                desc = vision_describe(src, lbl)
                if desc: descriptions[lbl] = desc

        print("\n[3/5] Generation textes cinema...")
        _fb   = pick_fallback(raw_paths[0][0] if raw_paths else "")
        texts = {"hook": _fb["hook"], "core": _fb["core"], "punch": _fb["punch"]}
        if cfg(opts, "ai_text"):
            result = generate_texts(descriptions, opts)
            if result:
                texts = result
                print(f"  OK HOOK  : {texts.get('hook')}")
                print(f"  OK CORE  : {texts.get('core')}")
                print(f"  OK PUNCH : {texts.get('punch')}")
            else:
                print("  API KO -> fallback")
        if cfg(opts, "custom_hook"):  texts["hook"]  = cfg(opts, "custom_hook")
        if cfg(opts, "custom_punch"): texts["punch"] = cfg(opts, "custom_punch")

        print("\n[4/5] Assemblage crossfade...")
        assemble_cinema(seg_paths, xfade, opts)

        print("\n[5/5] Overlay BD + logo LesCrados.Ai 5s anime...")
        build_cinema_overlay(texts, opts)

    # ── MODE PUNCH ───────────────────────────────────────────────────
    else:
        scdet_thr = cfg(opts, "scdet_thr")

        print("\n[1/7] Analyse metriques...")
        clips_meta = []
        for i, (path, user_role) in enumerate(raw_paths):
            m = extract_metrics(path, scdet_thr)
            m.update({"path": path, "index": i, "user_role": user_role})
            clips_meta.append(m)
            print(f"  Clip {i}: dur={m['duration']:.2f}s scenes={m['scene_count']}")

        print("\n[2/7] Scoring & ordre...")
        all_auto = all(m["user_role"] == "auto" for m in clips_meta)
        if cfg(opts, "auto_order") and all_auto:
            ordered = score_and_order(clips_meta)
        else:
            role_order = {"hook": 0, "core": 1, "punch": 2, "auto": 1}
            ordered = sorted(clips_meta, key=lambda m: role_order.get(m["user_role"], 1))
            for m in ordered:
                m["role"] = m["user_role"] if m["user_role"] != "auto" else "core"
            if len(ordered) == 1: ordered[0]["role"] = "hook"

        print("\n[3/7] Vision IA (Anthropic)...")
        descriptions = {}
        if ANTHROPIC_KEY and cfg(opts, "ai_text"):
            for m in ordered:
                role = m.get("role", "core")
                desc = vision_describe(m["path"], role)
                if desc: descriptions[role] = desc

        print("\n[4/7] Generation textes narratifs...")
        _fb = pick_fallback(raw_paths[0][0] if raw_paths else "")
        texts = {
            "hook":  cfg(opts, "custom_hook")  or _fb["hook"],
            "core":  _fb["core"],
            "punch": cfg(opts, "custom_punch") or _fb["punch"],
        }
        if cfg(opts, "ai_text"):
            result = generate_texts(descriptions, opts)
            if result:
                if cfg(opts, "custom_hook"):  result["hook"]  = cfg(opts, "custom_hook")
                if cfg(opts, "custom_punch"): result["punch"] = cfg(opts, "custom_punch")
                texts = result
                print(f"  Claude OK -- hook: {texts.get('hook')}")
            else:
                print(f"  API KO -> fallback: {_fb['hook']}")
        print(f"  HOOK  : {texts.get('hook')}")
        print(f"  CORE  : {texts.get('core')}")
        print(f"  PUNCH : {texts.get('punch')}")

        print("\n[5/7] Decoupe + effets...")
        dur_map = {
            "hook":  cfg(opts, "hook_dur"),
            "core":  cfg(opts, "core_dur"),
            "punch": cfg(opts, "punch_dur"),
        }
        tol = cfg(opts, "tolerance"); segments = []
        for m in ordered:
            role    = m.get("role", "core")
            target  = dur_map.get(role, 2.5)
            cut     = find_natural_cut(m["path"], target, tol, scdet_thr)
            seg_out = f"_seg_{m['index']}_{role}.mp4"
            print(f"  {role:5s}: {cut:.2f}s ...")
            build_punch_segment(m["path"], seg_out, cut, role, opts)
            segments.append((seg_out, role, cut))

        print("\n[6/7] Assemblage BD + overlay + logo 5s anime...")
        build_punch_final(segments, texts, opts)
        print("\n[7/7] output.mp4 genere")

    if os.path.isfile("output.mp4"):
        size = os.path.getsize("output.mp4")
        print(f"\n output.mp4 -- {size // 1024} KB")
        print(" Logo LesCrados.Ai 5s anime inclus en fin")
    else:
        print("\n output.mp4 absent !"); sys.exit(1)


if __name__ == "__main__":
    start()
