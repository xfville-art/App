"""
render.py — ViraCut Studio v6  ★ LesCrados Edition ★
Pipeline : auto / punch / cinéma
Améliorations v6 :
  - Textes repositionnés : hook haut / core bas (jamais au centre) / punch bas
  - Style BD Comics : double-bordure colorée, boîtes punchy
  - Flashes colorés (rouge/jaune) au lieu du blanc
  - Letterbox cinéma permanent (bars noires ciné)
  - Outro logo "LesCrados.Ai" Hollywood splash 2.5s
  - Colour grading renforcé style clip Hollywood
stdlib uniquement + FFmpeg + Gemini API (vision + textes)
"""
import json, base64, os, subprocess, urllib.request, urllib.error, time, sys

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

# Palette BD LesCrados
C_HOOK   = "#FF2442"   # rouge vif — hook
C_HOOK_B = "#FFD60A"   # jaune — bordure hook
C_CORE_B = "#FF2442"   # rouge — bordure core
C_PUNCH  = "#FF6B00"   # orange vif — fond punch
C_FLASH1 = "#FF2442"   # flash rouge (hook→core)
C_FLASH2 = "#FFD60A"   # flash jaune (core→punch)

DEFAULTS = {
    "mode": "auto", "resolution": "720x1280", "fps": 24, "crf": 18,
    "audio_br": 192, "fade_dur": 0.3, "ai_text": True,
    "custom_hook": "", "custom_punch": "",
    "hook_dur": 2.0, "core_dur": 2.5, "punch_dur": 3.0,
    "tolerance": 0.7, "flash_cut": True, "zoom_punch": True,
    "zoom_scale": 1.08, "auto_order": True, "scdet_thr": 10,
    "hook_size": 88, "punch_size": 64, "text_bg": False,
    "cinema_dur": 26, "cinema_clip_min": 7, "cinema_clip_max": 12,
    "cinema_xfade": 0.7, "cinema_kb_zoom": 1.09, "cinema_lb_h": 65,
}


# ═══════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════
def cfg(opts, key):
    return opts.get(key, DEFAULTS[key])


def run(cmd, check=True):
    print(f"    $ {cmd[:110]}{'…' if len(cmd)>110 else ''}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("STDERR:", r.stderr[-600:])
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
# [1] NORMALISATION — crop 9:16 + audio garanti
# ═══════════════════════════════════════════════════════════════════════
def normalize(src, out, opts):
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps")
    crf  = cfg(opts, "crf")
    abr  = cfg(opts, "audio_br")

    scale_crop = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps}")

    if has_audio(src):
        cmd = (f'ffmpeg -y -i "{src}" '
               f'-vf "{scale_crop}" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset ultrafast '
               f'-c:a aac -b:a {abr}k -ar 44100 -ac 2 '
               f'"{out}"')
    else:
        cmd = (f'ffmpeg -y -i "{src}" '
               f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
               f'-filter_complex "[0:v]{scale_crop}[v];[1:a]atrim=0:10[a]" '
               f'-map "[v]" -map "[a]" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset ultrafast '
               f'-c:a aac -b:a {abr}k '
               f'-shortest "{out}"')
    run(cmd)


# ═══════════════════════════════════════════════════════════════════════
# [2] EXTRACTION MULTI-MÉTRIQUES
# ═══════════════════════════════════════════════════════════════════════
def extract_metrics(path, scdet_thr=10):
    info = ffprobe(path)
    fmt  = info.get("format", {})
    dur  = float(fmt.get("duration", 0))

    rms = 40.0
    try:
        r = subprocess.run(
            f'ffmpeg -i "{path}" -af volumedetect -f null /dev/null 2>&1',
            shell=True, capture_output=True, text=True
        )
        out = r.stdout + r.stderr
        for line in out.split("\n"):
            if "mean_volume" in line:
                val = float(line.split(":")[-1].strip().split()[0])
                rms = val + 91
    except Exception:
        pass

    motion = 30.0
    try:
        r = subprocess.run(
            f'ffmpeg -i "{path}" -vf "mpdecimate,metadata=print:file=-" '
            f'-f null /dev/null 2>&1 | grep -c "lavfi.mpdecimate.drop=1" || echo 0',
            shell=True, capture_output=True, text=True
        )
        dropped = int((r.stdout + r.stderr).strip().split("\n")[0] or "0")
        motion = max(0.0, 60.0 - dropped * 2)
    except Exception:
        pass

    scene_count = 0
    try:
        r = subprocess.run(
            f'ffmpeg -i "{path}" -vf "select=gt(scene\\,{scdet_thr/100:.3f}),showinfo" '
            f'-f null /dev/null 2>&1 | grep -c "n:" || echo 0',
            shell=True, capture_output=True, text=True
        )
        scene_count = int((r.stdout + r.stderr).strip().split("\n")[0] or "0")
    except Exception:
        pass

    density = scene_count / max(dur, 1.0)

    return {
        "duration": dur, "scene_count": scene_count,
        "density": density, "rms": rms, "motion": motion,
    }


# ═══════════════════════════════════════════════════════════════════════
# [3] SCORING 3D → ordre hook → core → punch
# ═══════════════════════════════════════════════════════════════════════
def score_and_order(clips_meta):
    scored = []
    for m in clips_meta:
        d    = m["duration"]
        dens = m["density"]
        mot  = m["motion"]
        rms  = m["rms"]

        early = dens * 2
        late  = rms / 10.0

        h = early * 12 + m["scene_count"] * 0.5 + mot - d
        c = dens  *  8 + mot + d
        p = late  * 12 + rms - dens

        scored.append({**m, "hook_score": h, "core_score": c, "punch_score": p})

    n = len(scored)
    if n == 1:
        scored[0]["role"] = "hook"
    elif n == 2:
        by_hook = sorted(scored, key=lambda x: x["hook_score"], reverse=True)
        by_hook[0]["role"] = "hook"
        by_hook[1]["role"] = "punch"
        scored = by_hook
    else:
        by_hook = sorted(scored, key=lambda x: x["hook_score"], reverse=True)
        by_hook[0]["role"] = "hook"
        rest = sorted(by_hook[1:], key=lambda x: x["punch_score"], reverse=True)
        rest[0]["role"] = "punch"
        for r in rest[1:]:
            r["role"] = "core"
        scored = [by_hook[0]] + rest

    order = {"hook": 0, "core": 1, "punch": 2}
    scored.sort(key=lambda x: order.get(x.get("role", "core"), 1))
    return scored


# ═══════════════════════════════════════════════════════════════════════
# [4] DÉCOUPE AVEC CUT NATUREL
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
            shell=True, capture_output=True, text=True
        )
        for line in (r.stdout + r.stderr).split("\n"):
            if "pts_time:" in line:
                for part in line.split():
                    if part.startswith("pts_time:"):
                        try:
                            scene_times.append(float(part.split(":", 1)[1]))
                        except Exception:
                            pass
    except Exception:
        pass

    candidates = [t for t in scene_times
                  if target - tolerance <= t <= target + tolerance and t > 0]
    if candidates:
        return min(candidates, key=lambda t: abs(t - target))

    return min(target, vid_dur)


# ═══════════════════════════════════════════════════════════════════════
# [5] GEMINI API — Vision + génération textes
# ═══════════════════════════════════════════════════════════════════════

GEMINI_VISION_MODEL = "gemini-2.0-flash"
GEMINI_TEXT_MODEL   = "gemini-2.0-flash"
GEMINI_BASE_URL     = "https://generativelanguage.googleapis.com/v1beta/models"

import random, hashlib

FALLBACK_BANK = [
    {"hook": "CA SENT MAUVAIS", "core": "et pourtant il recommence",            "punch": "la prochaine carte sera pire"},
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


def extract_frame(path, t_ratio, out):
    dur = duration(path)
    t   = max(0.0, dur * t_ratio)
    subprocess.run(
        f'ffmpeg -y -ss {t:.2f} -i "{path}" -vframes 1 -q:v 3 "{out}" 2>/dev/null',
        shell=True
    )
    return os.path.isfile(out)


def gemini_call(model, parts, max_tokens=300, temperature=0.9):
    if not GEMINI_KEY:
        print("    [GEMINI] ❌ GEMINI_API_KEY absent")
        return None

    url     = f"{GEMINI_BASE_URL}/{model}:generateContent?key={GEMINI_KEY}"
    payload = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        }
    }).encode()

    for attempt in range(2):
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"    [GEMINI] HTTP {e.code}: {body}")
            if e.code in (400, 403):
                return None
        except Exception as e:
            print(f"    [GEMINI] Erreur: {e}")
        if attempt == 0:
            print("    [GEMINI] Retry dans 3s…")
            time.sleep(3)
    return None


def test_gemini():
    if not GEMINI_KEY:
        print("  Gemini  : ❌ clé absente")
        return False
    result = gemini_call(GEMINI_TEXT_MODEL, [{"text": "Réponds juste: OK"}], max_tokens=10, temperature=0)
    if result and "OK" in result.upper():
        print(f"  Gemini  : ✅ {GEMINI_VISION_MODEL} opérationnel")
        return True
    print(f"  Gemini  : ⚠ réponse inattendue: {result}")
    return bool(result)


def vision_describe(path, role):
    frames_b64 = []
    for ratio in [0.08, 0.28, 0.50, 0.72, 0.92]:
        frame_out = f"_frame_{role}_{int(ratio*100)}.jpg"
        if extract_frame(path, ratio, frame_out):
            with open(frame_out, "rb") as f:
                data = base64.b64encode(f.read()).decode()
                frames_b64.append(data)

    if not frames_b64:
        return ""

    parts = []
    for b64 in frames_b64:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64
            }
        })

    parts.append({
        "text": (
            f"Ces images sont extraites d'un clip vidéo (rôle narratif: {role}).\n"
            "Décris EN FRANÇAIS en 2-3 phrases courtes et précises :\n"
            "1. Le ou les personnages présents (apparence, nom visible si affiché)\n"
            "2. L'action principale qui se passe (ce qui est drôle, bizarre, dégoûtant)\n"
            "3. L'ambiance visuelle et l'élément le plus WTF/choquant\n"
            "Sois très spécifique et factuel sur ce que tu VOIS réellement."
        )
    })

    print(f"    [VISION] Analyse Gemini du clip {role}…")
    result = gemini_call(GEMINI_VISION_MODEL, parts, max_tokens=200, temperature=0.4)
    if result:
        print(f"    [VISION] {role}: {result[:100]}…")
        return result
    return ""


def generate_texts(descriptions, opts):
    desc_lines = "\n".join(
        f"[{role.upper()}] {desc}"
        for role, desc in descriptions.items() if desc
    ).strip()

    if not desc_lines:
        print("    [TEXTES] Aucune description disponible → fallback")
        return None

    custom_hook  = opts.get("custom_hook", "").strip() if opts else ""
    custom_punch = opts.get("custom_punch", "").strip() if opts else ""

    hook_instruction  = f'Pour le hook, utilise EXACTEMENT ce texte : "{custom_hook}"' if custom_hook else "Génère le hook basé sur le contenu réel."
    punch_instruction = f'Pour la punchline, utilise EXACTEMENT ce texte : "{custom_punch}"' if custom_punch else "Génère la punchline basée sur le contenu réel."

    prompt = f"""Tu es le rédacteur créatif de la chaîne TikTok LES CRADOS.
Style : humour absurde, crado, choquant, ironique. Aucune censure. Style Garbage Pail Kids version française.

CONTENU RÉEL DES CLIPS (décrit par IA vision) :
{desc_lines}

RÈGLES STRICTES :
- Les textes DOIVENT référencer ce qui se passe VRAIMENT dans les clips
- Aucun texte générique comme "une carte pour chaque horreur" ou "collectionne si tu oses"
- Le hook doit accrocher en moins de 2 secondes
- La punchline doit faire rire par son absurdité ou sa précision crado
- Aucun emoji, aucun caractère spécial, aucun accent (compatibilité FFmpeg)
- Tout en minuscules sauf le hook en MAJUSCULES

{hook_instruction}
{punch_instruction}

Réponds UNIQUEMENT avec ce JSON valide (aucun markdown, aucun texte avant/après) :
{{"hook":"4 MOTS MAX EN MAJUSCULES CHOC","core":"phrase courte 5-6 mots humour absurde sur ce qui se passe","punch":"chute 6-8 mots drole et specifique au contenu"}}"""

    print("    [TEXTES] Génération Gemini…")
    raw = gemini_call(GEMINI_TEXT_MODEL, [{"text": prompt}], max_tokens=200, temperature=1.0)
    if not raw:
        return None

    for fence in ["```json", "```"]:
        raw = raw.replace(fence, "")
    raw = raw.strip()

    try:
        result = json.loads(raw)
        print(f"    [TEXTES] hook={result.get('hook')} | core={result.get('core')} | punch={result.get('punch')}")
        return result
    except Exception:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(raw[start:end])
                print(f"    [TEXTES] (extrait) {result}")
                return result
            except Exception:
                pass
    print(f"    [TEXTES] Parse JSON échoué. Réponse brute : {raw[:200]}")
    return None


# ═══════════════════════════════════════════════════════════════════════
# ─── LOGO SPLASH "LesCrados.Ai" — outro Hollywood ─────────────────────
# ═══════════════════════════════════════════════════════════════════════

def build_logo_splash(out, opts):
    """
    Crée une séquence finale de 2.5s style carte de production Hollywood.
    Fond noir → "LES CRADOS" chrome géant → ".Ai" rouge → fade out.
    """
    W, H   = cfg(opts, "resolution").split("x")
    fps    = cfg(opts, "fps")
    crf    = cfg(opts, "crf")
    Wi, Hi = int(W), int(H)
    dur    = 2.5

    # Positions verticales
    y_les    = Hi // 2 - 185    # "LES" petit au-dessus
    y_crados = Hi // 2 - 100    # "CRADOS" géant centré
    y_ai     = Hi // 2 + 110    # ".Ai" accent rouge en dessous
    y_sub    = Hi // 2 + 200    # sous-texte discret

    # Effets de fade global (video fade in / out)
    fade_in  = f"fade=t=in:st=0:d=0.6:color=black"
    fade_out = f"fade=t=out:st=2.1:d=0.4:color=black"

    # Double bordure "LES" — silver style
    dt_les_shadow = (
        f"drawtext=fontfile={FONT}:text='LES':"
        f"fontsize=82:fontcolor=#888888:borderw=0:"
        f"x=(w-text_w)/2:y={y_les + 4}"
    )
    dt_les = (
        f"drawtext=fontfile={FONT}:text='LES':"
        f"fontsize=82:fontcolor=#DDDDDD:borderw=3:bordercolor=#444444:"
        f"x=(w-text_w)/2:y={y_les}"
    )

    # "CRADOS" — énorme, blanc chrome, double bordure (ombre + principal)
    dt_crados_shadow = (
        f"drawtext=fontfile={FONT}:text='CRADOS':"
        f"fontsize=195:fontcolor=#222222:borderw=0:"
        f"x=(w-text_w)/2+6:y={y_crados + 8}"
    )
    dt_crados_outer = (
        f"drawtext=fontfile={FONT}:text='CRADOS':"
        f"fontsize=195:fontcolor=#555555:borderw=14:bordercolor=#111111:"
        f"x=(w-text_w)/2:y={y_crados}"
    )
    dt_crados = (
        f"drawtext=fontfile={FONT}:text='CRADOS':"
        f"fontsize=195:fontcolor=white:borderw=6:bordercolor=#888888:"
        f"x=(w-text_w)/2:y={y_crados}"
    )

    # ".Ai" — rouge vif, accent couleur
    dt_ai = (
        f"drawtext=fontfile={FONT}:text='.Ai':"
        f"fontsize=90:fontcolor=#FF2442:borderw=5:bordercolor=#880011:"
        f"x=(w-text_w)/2:y={y_ai}"
    )

    # Ligne de sous-texte discret
    dt_sub = (
        f"drawtext=fontfile={FONT}:text='Les Crados':"
        f"fontsize=28:fontcolor=white@0.30:borderw=0:"
        f"x=(w-text_w)/2:y={y_sub}"
    )

    vf = (f"{dt_les_shadow},{dt_les},"
          f"{dt_crados_shadow},{dt_crados_outer},{dt_crados},"
          f"{dt_ai},{dt_sub},"
          f"{fade_in},{fade_out}")

    run(f'ffmpeg -y '
        f'-f lavfi -i "color=c=black:size={W}x{H}:rate={fps}" '
        f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
        f'-t {dur} '
        f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{dur}[a]" '
        f'-map "[v]" -map "[a]" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset ultrafast '
        f'-c:a aac -b:a 128k "{out}"')


def concat_with_logo(main_mp4, opts):
    """Concatène main_mp4 + logo splash → output.mp4."""
    crf = cfg(opts, "crf")
    abr = cfg(opts, "audio_br")

    print("  [LOGO] Build LesCrados.Ai splash…")
    build_logo_splash("_logo.mp4", opts)

    with open("_concat_logo.txt", "w") as f:
        f.write(f"file '{main_mp4}'\n")
        f.write("file '_logo.mp4'\n")

    run(f'ffmpeg -y -f concat -safe 0 -i _concat_logo.txt '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k '
        f'output.mp4')
    print("  [LOGO] ✅ Logo splash ajouté → output.mp4")


# ═══════════════════════════════════════════════════════════════════════
# ─── MODE PUNCH ───────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════

def build_punch_segment(src, out, cut_dur, role, opts):
    """Découpe + colour grading Hollywood + zoom punch (core) → segment normalisé."""
    W, H = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps")
    crf   = cfg(opts, "crf")
    abr   = cfg(opts, "audio_br")

    # Colour grading Hollywood par rôle
    if role == "hook":
        # Chaud / punch — saturation haute, contraste fort
        grade = "eq=saturation=1.55:brightness=0.05:contrast=1.18,hue=h=5"
    elif role == "core":
        # Neutre légèrement sombre — met en valeur les textes
        grade = "eq=saturation=1.10:brightness=-0.02:contrast=1.08"
    else:   # punch
        # Désaturé / froid / dramatique
        grade = "eq=saturation=0.65:brightness=-0.06:contrast=1.20,hue=h=-10"

    zoom_filter = ""
    if role == "core" and cfg(opts, "zoom_punch"):
        zs = cfg(opts, "zoom_scale")
        inc = (zs - 1.0) / max(cut_dur * fps, 1)
        zoom_expr = f"min(zoom+{inc:.6f},{zs})"
        zoom_filter = (
            f",zoompan=z='{zoom_expr}'"
            f":x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)'"
            f":d=1:s={W}x{H}:fps={fps}"
        )

    scale_crop = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps}")
    vf = f"{scale_crop},{grade}{zoom_filter}"

    if has_audio(src):
        cmd = (f'ffmpeg -y -ss 0 -t {cut_dur:.3f} -i "{src}" '
               f'-vf "{vf}" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
               f'-c:a aac -b:a {abr}k -ar 44100 -ac 2 '
               f'-shortest "{out}"')
    else:
        cmd = (f'ffmpeg -y -ss 0 -t {cut_dur:.3f} -i "{src}" '
               f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
               f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{cut_dur:.3f}[a]" '
               f'-map "[v]" -map "[a]" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
               f'-c:a aac -b:a {abr}k '
               f'-shortest "{out}"')
    run(cmd)


def build_flash(out, opts, color="white"):
    """1 frame colorée entre les segments (rouge ou jaune au lieu de blanc)."""
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps")
    dur  = round(1.0 / fps, 6)
    run(f'ffmpeg -y '
        f'-f lavfi -i "color=c={color}:size={W}x{H}:rate={fps}" '
        f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
        f'-t {dur} -c:v libx264 -pix_fmt yuv420p -crf 18 -preset ultrafast '
        f'-c:a aac -b:a 128k "{out}"')
    return dur


def build_punch_final(segments, texts, opts):
    """
    Assemble les segments (+ flash BD colorés) et applique les textes animés.
    Textes repositionnés style BD — jamais au centre de l'image.
    Fin : concat logo LesCrados.Ai.
    segments : [(path, role, dur), ...]
    texts    : {hook, core, punch}
    """
    W, H = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps")
    crf   = cfg(opts, "crf")
    abr   = cfg(opts, "audio_br")
    fade  = cfg(opts, "fade_dur")
    Wi, Hi = int(W), int(H)

    hook_sz  = cfg(opts, "hook_size")     # 88px
    punch_sz = cfg(opts, "punch_size")    # 64px
    core_sz  = int(hook_sz * 0.80)        # ~70px

    hook_txt  = escape_ffmpeg(texts.get("hook",  "TAS VU CA"))
    core_txt  = escape_ffmpeg(texts.get("core",  "incroyable mais vrai"))
    punch_txt = escape_ffmpeg(texts.get("punch", "une carte a collectionner"))

    # ── Flash cuts BD (rouge entre hook→core, jaune entre core→punch) ─
    flash_dur = 0.0
    flash_paths = []
    if cfg(opts, "flash_cut"):
        flash_colors = [C_FLASH1, C_FLASH2, C_FLASH1]
        for i in range(len(segments) - 1):
            fp    = f"_flash_{i}.mp4"
            color = flash_colors[i % len(flash_colors)]
            flash_dur = build_flash(fp, opts, color=color)
            flash_paths.append(fp)

    # ── concat.txt ─────────────────────────────────────────────────────
    with open("concat.txt", "w") as f:
        for i, (path, role, _dur) in enumerate(segments):
            f.write(f"file '{path}'\n")
            if i < len(segments) - 1 and flash_paths:
                f.write(f"file '{flash_paths[i]}'\n")

    run("ffmpeg -y -f concat -safe 0 -i concat.txt -c copy _base.mp4")

    # ── Calcul des offsets temporels ───────────────────────────────────
    t_map = {}
    t = 0.0
    for i, (path, role, dur) in enumerate(segments):
        if role not in t_map:
            t_map[role] = (t, t + dur)
        t += dur
        if i < len(segments) - 1 and flash_paths:
            t += flash_dur
    total = t

    h_s, h_e = t_map.get("hook",  (0.0,   2.0))
    c_s, c_e = t_map.get("core",  (h_e,   h_e + 2.5))
    p_s, p_e = t_map.get("punch", (c_e,   total))

    # ══════════════════════════════════════════════════════════════════
    # TEXTES STYLE BD — POSITIONNEMENT
    # ══════════════════════════════════════════════════════════════════
    # Letterbox Hollywood: barres noires haut (60px) et bas (70px)
    lb_top = 60
    lb_bot = 70
    lb_y_b = Hi - lb_bot

    # ── HOOK : bande du haut, couleur rouge vif ──────────────────────
    # Slide depuis le haut (animation 0.20s)
    hook_anim_dur = 0.20
    hook_y_final  = lb_top // 2 - hook_sz // 2   # centré dans barre du haut
    hook_y_final  = max(8, hook_y_final)
    slide_up_y = (
        f"if(lt(t-{h_s:.3f},{hook_anim_dur}),"
        f"(-{hook_sz})+(t-{h_s:.3f})/{hook_anim_dur}*({hook_y_final}+{hook_sz}),"
        f"{hook_y_final})"
    )

    # ── CORE : bande basse (70% de l'écran), pas au centre ──────────
    # Position y = 72% de la hauteur
    core_y = int(Hi * 0.72)
    core_anim_dur = 0.15
    core_alpha = (
        f"if(lt(t-{c_s:.3f},{core_anim_dur}),"
        f"(t-{c_s:.3f})/{core_anim_dur},"
        f"1)"
    )

    # ── PUNCH : bande du bas ─────────────────────────────────────────
    punch_y_final = lb_y_b + lb_bot // 2 - punch_sz // 2
    punch_y_final = min(Hi - punch_sz - 8, punch_y_final)
    punch_anim_dur = 0.18
    slide_dn_y = (
        f"if(lt(t-{p_s:.3f},{punch_anim_dur}),"
        f"h+(0-{punch_anim_dur}-(t-{p_s:.3f}))*-1/{punch_anim_dur}*"
        f"(h-{punch_y_final}),"
        f"{punch_y_final})"
    )
    # Simplified version: slide from bottom
    slide_dn_y = (
        f"if(lt(t-{p_s:.3f},{punch_anim_dur}),"
        f"h-{punch_sz}+(h-{punch_y_final})*(1-(t-{p_s:.3f})/{punch_anim_dur}),"
        f"{punch_y_final})"
    )

    # ══════════════════════════════════════════════════════════════════
    # FILTRES DRAWBOX + DRAWTEXT
    # ══════════════════════════════════════════════════════════════════

    # Letterbox ciné (permanent)
    lb_filters = (
        f"drawbox=x=0:y=0:w={W}:h={lb_top}:color=black@0.95:t=fill,"
        f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_bot}:color=black@0.95:t=fill"
    )

    # ── HOOK box rouge + texte double bordure BD ─────────────────────
    dt_hook_box = (
        f"drawbox=x=0:y=0:w={W}:h={lb_top}:"
        f"color={C_HOOK}@0.85:t=fill:"
        f"enable='between(t,{h_s:.3f},{h_e:.3f})'"
    )
    # Couche ombre (décalée +3px) pour effet profondeur
    dt_hook_shadow = (
        f"drawtext=fontfile={FONT}:text='{hook_txt}':"
        f"fontsize={hook_sz}:fontcolor=#880011:borderw=0:"
        f"x=(w-text_w)/2+3:y='{slide_up_y.replace('hook_y_final', str(hook_y_final + 3))}':"
        f"enable='between(t,{h_s:.3f},{h_e:.3f})'"
    )
    # Couche principale (blanc + bordure jaune épaisse)
    dt_hook = (
        f"drawtext=fontfile={FONT}:text='{hook_txt}':"
        f"fontsize={hook_sz}:fontcolor=white:borderw=8:bordercolor={C_HOOK_B}:"
        f"x=(w-text_w)/2:y='{slide_up_y}':"
        f"enable='between(t,{h_s:.3f},{h_e:.3f})'"
    )

    # ── CORE box sombre + texte fade-in couleur BD ───────────────────
    dt_core_box = (
        f"drawbox=x=0:y={core_y - core_sz - 8}:w={W}:h={core_sz + 20}:"
        f"color=black@0.72:t=fill:"
        f"enable='between(t,{c_s:.3f},{c_e:.3f})'"
    )
    # Ligne décorative rouge à gauche style BD
    dt_core_accent = (
        f"drawbox=x=0:y={core_y - core_sz - 8}:w=8:h={core_sz + 20}:"
        f"color={C_HOOK}@0.95:t=fill:"
        f"enable='between(t,{c_s:.3f},{c_e:.3f})'"
    )
    dt_core = (
        f"drawtext=fontfile={FONT}:text='{core_txt}':"
        f"fontsize={core_sz}:fontcolor=white:borderw=4:bordercolor={C_CORE_B}:"
        f"x=(w-text_w)/2:y={core_y - core_sz}:"
        f"alpha='{core_alpha}':"
        f"enable='between(t,{c_s:.3f},{c_e:.3f})'"
    )

    # ── PUNCH box orange vif + texte blanc gras ───────────────────────
    dt_punch_box = (
        f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_bot}:"
        f"color={C_PUNCH}@0.95:t=fill:"
        f"enable='between(t,{p_s:.3f},{p_e:.3f})'"
    )
    dt_punch = (
        f"drawtext=fontfile={FONT}:text='{punch_txt}':"
        f"fontsize={punch_sz}:fontcolor=white:borderw=5:bordercolor=#882200:"
        f"x=(w-text_w)/2:y='{slide_dn_y}':"
        f"enable='between(t,{p_s:.3f},{p_e:.3f})'"
    )

    # ── Logo watermark discret ────────────────────────────────────────
    logo_wm = (
        f"drawtext=fontfile={FONT}:text='LesCrados.Ai':"
        f"fontsize=20:fontcolor=white@0.28:borderw=0:"
        f"x=w-text_w-14:y={lb_y_b + lb_bot // 2 - 10}"
    )

    vf = ",".join([
        lb_filters,
        dt_hook_box, dt_hook_shadow, dt_hook,
        dt_core_box, dt_core_accent, dt_core,
        dt_punch_box, dt_punch,
        logo_wm,
    ])
    af = f"afade=t=out:st={max(0.0, total - fade):.3f}:d={fade}"

    run(f'ffmpeg -y -i _base.mp4 '
        f'-vf "{vf}" '
        f'-af "{af}" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k '
        f'_premain.mp4')

    # ── Concat logo splash final ───────────────────────────────────────
    build_logo_splash("_logo.mp4", opts)

    with open("_concat_logo.txt", "w") as f:
        f.write("file '_premain.mp4'\n")
        f.write("file '_logo.mp4'\n")

    run(f'ffmpeg -y -f concat -safe 0 -i _concat_logo.txt '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k '
        f'output.mp4')


# ═══════════════════════════════════════════════════════════════════════
# ─── MODE CINÉMA ──────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════

def build_cinema_segment(src, seg_out, clip_dur, kb_zoom, opts):
    """Clip normalisé + Ken Burns (zoom lent) + grading Hollywood."""
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps")
    crf  = cfg(opts, "crf")
    abr  = cfg(opts, "audio_br")

    scale_crop = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps}")

    # Grading ciné : légère désaturation + contraste Hollywood
    grade = "eq=saturation=0.90:brightness=-0.03:contrast=1.15"

    frames = clip_dur * fps
    inc    = (kb_zoom - 1.0) / max(frames, 1)
    kb_z   = f"min(zoom+{inc:.6f},{kb_zoom})"
    kb_filter = (
        f"zoompan=z='{kb_z}'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d=1:s={W}x{H}:fps={fps}"
    )

    vf = f"{scale_crop},{grade},{kb_filter}"

    if has_audio(src):
        cmd = (f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" '
               f'-vf "{vf}" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
               f'-c:a aac -b:a {abr}k -ar 44100 -ac 2 '
               f'-shortest "{seg_out}"')
    else:
        cmd = (f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" '
               f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
               f'-filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{clip_dur:.2f}[a]" '
               f'-map "[v]" -map "[a]" '
               f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
               f'-c:a aac -b:a {abr}k '
               f'-shortest "{seg_out}"')
    run(cmd)


def assemble_cinema(seg_paths, xfade_dur, opts):
    """Enchaîne les segments avec crossfade xfade."""
    crf = cfg(opts, "crf")
    abr = cfg(opts, "audio_br")
    n   = len(seg_paths)

    if n == 1:
        import shutil
        shutil.copy(seg_paths[0], "_assembled.mp4")
        return

    inputs = " ".join(f'-i "{p}"' for p in seg_paths)
    durs   = [duration(p) for p in seg_paths]

    v_parts, a_parts = [], []
    offset = durs[0] - xfade_dur
    prev_v, prev_a = "[0:v]", "[0:a]"

    for i in range(1, n):
        next_v = f"[xv{i}]" if i < n - 1 else "[vfin]"
        next_a = f"[xa{i}]" if i < n - 1 else "[afin]"
        v_parts.append(f"{prev_v}[{i}:v]xfade=transition=fade"
                       f":duration={xfade_dur:.2f}:offset={offset:.3f}{next_v}")
        a_parts.append(f"{prev_a}[{i}:a]acrossfade=d={xfade_dur:.2f}"
                       f":c1=tri:c2=tri{next_a}")
        prev_v, prev_a = next_v, next_a
        offset += durs[i] - xfade_dur

    fc = ";".join(v_parts + a_parts)
    run(f'ffmpeg -y {inputs} '
        f'-filter_complex "{fc}" '
        f'-map "[vfin]" -map "[afin]" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k '
        f'_assembled.mp4')


def build_cinema_overlay(texts, opts):
    """
    Applique letterbox + textes BD repositionnés sur _assembled.mp4 → _premain.mp4.
    Textes :
      HOOK  → dans la barre du haut (letterbox), rouge + jaune
      CORE  → bas de cadre (72% hauteur), fond sombre + accent rouge
      PUNCH → barre du bas (letterbox), fond orange vif
    Fin → concat logo LesCrados.Ai splash.
    """
    W, H   = cfg(opts, "resolution").split("x")
    lb_h   = cfg(opts, "cinema_lb_h")   # 65px
    crf    = cfg(opts, "crf")
    abr    = cfg(opts, "audio_br")
    fade   = cfg(opts, "fade_dur")
    Wi, Hi = int(W), int(H)

    # Barres cinéma plus épaisses pour style Hollywood (top 80 / bot 80)
    lb_top = max(lb_h, 80)
    lb_bot = max(lb_h, 80)
    lb_y_b = Hi - lb_bot

    total = duration("_assembled.mp4")
    # Timeline : hook (0-20%), core (20-72%), punch (72-100%)
    h_e   = total * 0.20
    mid_s = total * 0.20
    mid_e = total * 0.72
    fin_s = total * 0.72

    hook_txt  = escape_ffmpeg(texts.get("hook",  "LES CRADOS"))
    core_txt  = escape_ffmpeg(texts.get("core",  "incroyable mais vrai"))
    punch_txt = escape_ffmpeg(texts.get("punch", "une carte a collectionner"))

    hook_sz  = 56   # taille dans la letterbox top
    core_sz  = 50
    punch_sz = 48
    core_y   = int(Hi * 0.72)

    # ── Letterbox Hollywood permanent ─────────────────────────────────
    lb = (f"drawbox=x=0:y=0:w={W}:h={lb_top}:color=black@0.95:t=fill,"
          f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_bot}:color=black@0.95:t=fill")

    # ── HOOK dans barre du haut — fond rouge, texte blanc / bordure jaune
    dt_hook_bg = (
        f"drawbox=x=0:y=0:w={W}:h={lb_top}:"
        f"color={C_HOOK}@0.88:t=fill:"
        f"enable='between(t,0,{h_e:.2f})'"
    )
    hook_y = lb_top // 2 - hook_sz // 2
    _hook_display = hook_txt if hook_txt not in ('LES CRADOS', 'LES\\ CRADOS') else ''
    dt_hook = (
        f"drawtext=fontfile={FONT}:text='{_hook_display}':"
        f"fontsize={hook_sz}:fontcolor=white:borderw=7:bordercolor={C_HOOK_B}:"
        f"x=(w-text_w)/2:y={hook_y}:"
        f"enable='between(t,0,{h_e:.2f})'"
    ) if _hook_display else ""

    # ── CORE bas de cadre — fond sombre + accent rouge ────────────────
    box_core = (
        f"drawbox=x=0:y={core_y - core_sz - 10}:w={W}:h={core_sz + 22}:"
        f"color=black@0.75:t=fill:"
        f"enable='between(t,{mid_s:.2f},{mid_e:.2f})'"
    )
    core_accent = (
        f"drawbox=x=0:y={core_y - core_sz - 10}:w=8:h={core_sz + 22}:"
        f"color={C_HOOK}@0.95:t=fill:"
        f"enable='between(t,{mid_s:.2f},{mid_e:.2f})'"
    )
    sub = (
        f"drawtext=fontfile={FONT}:text='{core_txt}':"
        f"fontsize={core_sz}:fontcolor=white:borderw=4:bordercolor={C_CORE_B}:"
        f"x=(w-text_w)/2:y={core_y - core_sz}:"
        f"enable='between(t,{mid_s:.2f},{mid_e:.2f})'"
    )

    # ── PUNCH dans barre du bas — fond orange vif ─────────────────────
    punch_box = (
        f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_bot}:"
        f"color={C_PUNCH}@0.95:t=fill:"
        f"enable='between(t,{fin_s:.2f},{total:.2f})'"
    )
    punch_y = lb_y_b + lb_bot // 2 - punch_sz // 2
    punch = (
        f"drawtext=fontfile={FONT}:text='{punch_txt}':"
        f"fontsize={punch_sz}:fontcolor=white:borderw=5:bordercolor=#882200:"
        f"x=(w-text_w)/2:y={punch_y}:"
        f"enable='between(t,{fin_s:.2f},{total:.2f})'"
    )

    # ── Logo watermark ─────────────────────────────────────────────────
    logo_wm = (
        f"drawtext=fontfile={FONT}:text='LesCrados.Ai':"
        f"fontsize=20:fontcolor=white@0.28:borderw=0:"
        f"x=w-text_w-14:y={lb_y_b + lb_bot // 2 - 10}"
    )

    parts = [lb, dt_hook_bg] + ([dt_hook] if dt_hook else []) + \
            [box_core, core_accent, sub, punch_box, punch, logo_wm]
    vf = ",".join(p for p in parts if p)
    af = f"afade=t=out:st={max(0.0, total - fade):.3f}:d={fade}"

    run(f'ffmpeg -y -i _assembled.mp4 '
        f'-vf "{vf}" '
        f'-af "{af}" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k '
        f'_premain.mp4')

    # ── Concat logo splash LesCrados.Ai ───────────────────────────────
    print("  [LOGO] Build LesCrados.Ai splash…")
    build_logo_splash("_logo.mp4", opts)

    with open("_concat_logo.txt", "w") as f:
        f.write("file '_premain.mp4'\n")
        f.write("file '_logo.mp4'\n")

    run(f'ffmpeg -y -f concat -safe 0 -i _concat_logo.txt '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k '
        f'output.mp4')


# ═══════════════════════════════════════════════════════════════════════
# ─── ENTRY POINT ──────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════
def start():
    if not os.path.exists("p.json"):
        print("❌ p.json manquant"); sys.exit(1)

    with open("p.json") as f:
        data = json.load(f)

    clips_raw = data.get("videos", [])
    opts      = data.get("options", {})
    mode      = cfg(opts, "mode")
    api_key   = GEMINI_KEY

    print("═" * 52)
    print("  ViraCut render.py v6 — LesCrados Edition")
    print(f"  Mode    : {mode}  |  Clips : {len(clips_raw)}")
    test_gemini()
    print("═" * 52)

    if not clips_raw:
        print("❌ Aucun clip reçu"); sys.exit(1)

    # ── Decode raw clips ──────────────────────────────────────────────
    raw_paths = []
    for i, v in enumerate(clips_raw):
        raw = f"_raw_{i}.mp4"
        with open(raw, "wb") as f:
            f.write(base64.b64decode(v["data"]))
        raw_paths.append((raw, v.get("role", "auto")))
        print(f"  Clip {i}: {raw}  rôle={v.get('role','auto')}")

    # ── Résolution auto du mode ───────────────────────────────────────
    if mode == "auto":
        total_dur = sum(duration(p) for p, _ in raw_paths)
        if len(raw_paths) == 1 or total_dur > 12.0:
            mode = "cinema"
        else:
            mode = "punch"
        print(f"\n  Mode AUTO → {mode.upper()} "
              f"(durée totale clips : {total_dur:.1f}s)")

    # ══════════════════════════════════════════════════════════════════
    # ─── MODE CINÉMA ─────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════
    if mode == "cinema":
        n       = len(raw_paths)
        target  = cfg(opts, "cinema_dur")
        cmin    = cfg(opts, "cinema_clip_min")
        cmax    = cfg(opts, "cinema_clip_max")
        xfade   = cfg(opts, "cinema_xfade")
        kb_zoom = cfg(opts, "cinema_kb_zoom")

        clip_dur = min(cmax, max(cmin,
                      (target - xfade * (n - 1)) / n))

        print(f"\n[1/5] Segments Ken Burns Hollywood ({n}×{clip_dur:.1f}s)…")
        seg_paths = []
        for i, (src, role) in enumerate(raw_paths):
            seg_out = f"_cin_{i}.mp4"
            print(f"  Segment {i} ({role})…")
            build_cinema_segment(src, seg_out, clip_dur, kb_zoom, opts)
            seg_paths.append(seg_out)

        print("\n[2/5] Vision IA + descriptions…")
        descriptions = {}
        if api_key and cfg(opts, "ai_text"):
            for i, (src, role) in enumerate(raw_paths):
                lbl = role if role != "auto" else f"clip{i}"
                print(f"  Vision clip {i} ({lbl})…")
                desc = vision_describe(src, lbl)
                if desc:
                    descriptions[lbl] = desc
                    print(f"    → {desc[:90]}")

        print("\n[3/5] Génération textes cinéma…")
        _fb = pick_fallback(raw_paths[0][0] if raw_paths else "")
        texts = {
            "hook":  _fb["hook"],
            "core":  _fb["core"],
            "punch": _fb["punch"],
        }
        if cfg(opts, "ai_text"):
            result = generate_texts(descriptions, opts)
            if result:
                texts = result
                print(f"  ✅ HOOK  : {texts.get('hook')}")
                print(f"  ✅ CORE  : {texts.get('core')}")
                print(f"  ✅ PUNCH : {texts.get('punch')}")
            else:
                print(f"  ⚠ Gemini KO → fallback: {_fb['hook']} / {_fb['core']}")

        if cfg(opts, "custom_hook"):
            texts["hook"] = cfg(opts, "custom_hook")
        if cfg(opts, "custom_punch"):
            texts["punch"] = cfg(opts, "custom_punch")

        print("\n[4/5] Assemblage crossfade…")
        assemble_cinema(seg_paths, xfade, opts)

        print("\n[5/5] Letterbox BD + overlay + logo LesCrados.Ai…")
        build_cinema_overlay(texts, opts)

    # ══════════════════════════════════════════════════════════════════
    # ─── MODE PUNCH ──────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════
    else:
        scdet_thr = cfg(opts, "scdet_thr")

        print("\n[1/7] Extraction + analyse multi-métriques…")
        clips_meta = []
        for i, (path, user_role) in enumerate(raw_paths):
            print(f"  Clip {i} analyse…")
            m = extract_metrics(path, scdet_thr)
            m.update({"path": path, "index": i, "user_role": user_role})
            clips_meta.append(m)
            print(f"    dur={m['duration']:.2f}s  scènes={m['scene_count']}"
                  f"  rms={m['rms']:.1f}  motion={m['motion']:.1f}")

        print("\n[2/7] Classification narrative (scoring 3D)…")
        all_auto = all(m["user_role"] == "auto" for m in clips_meta)
        if cfg(opts, "auto_order") and all_auto:
            ordered = score_and_order(clips_meta)
        else:
            role_order = {"hook": 0, "core": 1, "punch": 2, "auto": 1}
            ordered = sorted(clips_meta,
                             key=lambda m: role_order.get(m["user_role"], 1))
            for m in ordered:
                m["role"] = m["user_role"] if m["user_role"] != "auto" else "core"
            if len(ordered) == 1:
                ordered[0]["role"] = "hook"

        for m in ordered:
            print(f"  {m.get('role','?'):5s} ← clip {m['index']} "
                  f"(dur={m['duration']:.1f}s "
                  f"hook={m.get('hook_score',0):.1f} "
                  f"punch={m.get('punch_score',0):.1f})")

        print("\n[3/7] Vision IA (Gemini) — 5 frames / clip…")
        descriptions = {}
        if api_key and cfg(opts, "ai_text"):
            for m in ordered:
                role = m.get("role", "core")
                print(f"  Vision {role}…")
                desc = vision_describe(m["path"], role)
                if desc:
                    descriptions[role] = desc
                    print(f"    → {desc[:90]}")

        print("\n[4/7] Génération textes narratifs…")
        _fb = pick_fallback(raw_paths[0][0] if raw_paths else "")
        texts = {
            "hook":  cfg(opts, "custom_hook")  or _fb["hook"],
            "core":  _fb["core"],
            "punch": cfg(opts, "custom_punch") or _fb["punch"],
        }
        if cfg(opts, "ai_text"):
            result = generate_texts(descriptions, opts)
            if result:
                if cfg(opts, "custom_hook"):
                    result["hook"] = cfg(opts, "custom_hook")
                if cfg(opts, "custom_punch"):
                    result["punch"] = cfg(opts, "custom_punch")
                texts = result
                print(f"  ✅ Gemini OK")
            else:
                print(f"  ⚠ Gemini KO → fallback: {_fb['hook']}")
        print(f"  HOOK    : {texts.get('hook')}")
        print(f"  CORE    : {texts.get('core')}")
        print(f"  PUNCH   : {texts.get('punch')}")

        print("\n[5/7] Découpe + effets par segment…")
        dur_map = {
            "hook":  cfg(opts, "hook_dur"),
            "core":  cfg(opts, "core_dur"),
            "punch": cfg(opts, "punch_dur"),
        }
        tol = cfg(opts, "tolerance")

        segments = []
        for m in ordered:
            role   = m.get("role", "core")
            target = dur_map.get(role, 2.5)
            cut    = find_natural_cut(m["path"], target, tol, scdet_thr)
            seg_out = f"_seg_{m['index']}_{role}.mp4"
            print(f"  {role:5s} : {cut:.2f}s (target={target}s) …")
            build_punch_segment(m["path"], seg_out, cut, role, opts)
            segments.append((seg_out, role, cut))

        print("\n[6/7] Assemblage BD + textes animés + audio + logo…")
        build_punch_final(segments, texts, opts)

        print("\n[7/7] output.mp4 généré ✓")

    # Vérification finale
    if os.path.isfile("output.mp4"):
        size = os.path.getsize("output.mp4")
        print(f"\n✅ output.mp4 — {size // 1024} KB")
        print("✅ LesCrados.Ai logo splash inclus en fin de vidéo")
    else:
        print("\n❌ output.mp4 absent !")
        sys.exit(1)


if __name__ == "__main__":
    start()
