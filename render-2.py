"""
render.py — ViraCut Studio v5
Pipeline : auto / punch / cinéma
stdlib uniquement + FFmpeg + Anthropic API (optionnel)
"""
import json, base64, os, subprocess, urllib.request, urllib.error, time, sys

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

# Defaults (alignés sur App-2.html getConfig())
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
    """Supprime les emojis et caractères non-ASCII pour FFmpeg/Liberation."""
    return ''.join(c for c in text if ord(c) < 128).strip()

def escape_ffmpeg(text):
    """Strip emojis puis échappe pour drawtext FFmpeg."""
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

    # Audio RMS → proxy énergie (volumedetect)
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
                rms = val + 91  # dBFS → 0-100 proxy
    except Exception:
        pass

    # Motion score via mpdecimate (frames ignorées = peu de mouvement)
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

    # Scènes détectées
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

        # Activité précoce proxy
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

    # Extraire les timestamps de changement de scène
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

    # Chercher un cut naturel dans la fenêtre [target−tol, target+tol]
    candidates = [t for t in scene_times
                  if target - tolerance <= t <= target + tolerance and t > 0]
    if candidates:
        return min(candidates, key=lambda t: abs(t - target))

    return min(target, vid_dur)


# ═══════════════════════════════════════════════════════════════════════
# [5] ANTHROPIC API — Vision + génération textes
# ═══════════════════════════════════════════════════════════════════════
def extract_frame(path, t_ratio, out):
    dur = duration(path)
    t   = max(0.0, dur * t_ratio)
    subprocess.run(
        f'ffmpeg -y -ss {t:.2f} -i "{path}" -vframes 1 -q:v 3 "{out}" 2>/dev/null',
        shell=True
    )
    return os.path.isfile(out)


def api_call(payload_dict):
    payload = json.dumps(payload_dict).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"    API error: {e}")
        return None


def vision_describe(path, role):
    """3 frames → description contenu + émotion + thème."""
    frames_b64 = []
    for ratio in [0.10, 0.50, 0.85]:
        frame_out = f"_frame_{role}_{int(ratio*100)}.jpg"
        if extract_frame(path, ratio, frame_out):
            with open(frame_out, "rb") as f:
                frames_b64.append(base64.b64encode(f.read()).decode())

    if not frames_b64:
        return ""

    content = [
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/jpeg", "data": b}}
        for b in frames_b64
    ]
    content.append({
        "type": "text",
        "text": (f"Clip rôle={role}. En 1 phrase courte et précise : "
                 "contenu principal, émotion dominante, thème visuel.")
    })

    resp = api_call({
        "model": "claude-sonnet-4-6",
        "max_tokens": 150,
        "messages": [{"role": "user", "content": content}]
    })
    if resp:
        return resp.get("content", [{}])[0].get("text", "").strip()
    return ""


def generate_texts(descriptions, opts):
    """Génère hook + core + punchline à partir des descriptions visuelles."""
    desc_lines = "\n".join(
        f"- {role}: {desc}" for role, desc in descriptions.items() if desc
    )
    if not desc_lines:
        return None

    prompt = (
        "Tu crées du texte TikTok viral pour la chaîne Les Crados "
        "(humour absurde crado, style Garbage Pail Kids).\n\n"
        f"Descriptions des clips :\n{desc_lines}\n\n"
        "Génère EXACTEMENT ce JSON (sans markdown, sans explication) :\n"
        '{"hook":"4 MOTS MAX MAJUSCULES CHOC WTF",'
        '"core":"5 mots humour absurde crado",'
        '"punch":"6 mots chute absurde SANS emoji SANS caractere special"}'
    )

    resp = api_call({
        "model": "claude-sonnet-4-6",
        "max_tokens": 150,
        "messages": [{"role": "user", "content": prompt}]
    })
    if not resp:
        return None

    raw = resp.get("content", [{}])[0].get("text", "").strip()
    # Nettoyer les balises markdown éventuelles
    for fence in ["```json", "```"]:
        raw = raw.replace(fence, "")
    raw = raw.strip()

    try:
        return json.loads(raw)
    except Exception:
        # Fallback : extraire depuis la première accolade
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except Exception:
                pass
    return None


# ═══════════════════════════════════════════════════════════════════════
# ─── MODE PUNCH ───────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════

def build_punch_segment(src, out, cut_dur, role, opts):
    """Découpe + colour grading + zoom punch (core) → segment normalisé."""
    W, H = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps")
    crf   = cfg(opts, "crf")
    abr   = cfg(opts, "audio_br")

    # Colour grading par rôle
    if role == "hook":
        grade = "eq=saturation=1.35:brightness=0.04:contrast=1.1,hue=h=4"
    elif role == "core":
        grade = "eq=saturation=1.0:brightness=0.0:contrast=1.0"
    else:   # punch
        grade = "eq=saturation=0.72:brightness=-0.04:contrast=1.12,hue=h=-8"

    # Zoom punch sur le core (zoompan, court donc rapide)
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


def build_flash(out, opts):
    """1 frame blanche entre les segments."""
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps")
    dur  = round(1.0 / fps, 6)
    run(f'ffmpeg -y '
        f'-f lavfi -i "color=c=white:size={W}x{H}:rate={fps}" '
        f'-f lavfi -i "anullsrc=r=44100:cl=stereo" '
        f'-t {dur} -c:v libx264 -pix_fmt yuv420p -crf 18 -preset ultrafast '
        f'-c:a aac -b:a 128k "{out}"')
    return dur


def build_punch_final(segments, texts, opts):
    """
    Assemble les segments (+ flash cuts) et applique les textes animés.
    segments : [(path, role, dur), ...]
    texts    : {hook, core, punch}
    """
    W, H = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps")
    crf   = cfg(opts, "crf")
    abr   = cfg(opts, "audio_br")
    fade  = cfg(opts, "fade_dur")

    hook_sz  = cfg(opts, "hook_size")
    punch_sz = cfg(opts, "punch_size")
    core_sz  = int(punch_sz * 0.85)

    hook_txt  = escape_ffmpeg(texts.get("hook",  "TAS VU CA"))
    core_txt  = escape_ffmpeg(texts.get("core",  "incroyable mais vrai"))
    punch_txt = escape_ffmpeg(texts.get("punch", "c'etait previsible !"))

    # ── Flash cuts ──────────────────────────────────────────────────
    flash_dur = 0.0
    flash_paths = []
    if cfg(opts, "flash_cut"):
        for i in range(len(segments) - 1):
            fp = f"_flash_{i}.mp4"
            flash_dur = build_flash(fp, opts)
            flash_paths.append(fp)

    # ── concat.txt ──────────────────────────────────────────────────
    with open("concat.txt", "w") as f:
        for i, (path, role, _dur) in enumerate(segments):
            f.write(f"file '{path}'\n")
            if i < len(segments) - 1 and flash_paths:
                f.write(f"file '{flash_paths[i]}'\n")

    run("ffmpeg -y -f concat -safe 0 -i concat.txt -c copy _base.mp4")

    # ── Calcul des offsets avec flash ────────────────────────────────
    t_map = {}   # role → (t_start, t_end)
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

    # ── Filtres drawtext ────────────────────────────────────────────
    # HOOK : slide depuis le haut (0.25s)
    slide_up_y = (f"if(lt(t-{h_s:.3f},0.25),"
                  f"-{hook_sz}+(t-{h_s:.3f})/0.25*({int(H)//14}+{hook_sz}),"
                  f"{int(H)//14})")
    # CORE : fade-in centré (0.20s)
    fade_alpha = (f"if(lt(t-{c_s:.3f},0.20),"
                  f"(t-{c_s:.3f})/0.20,1)")
    # PUNCH : slide depuis le bas (0.25s)
    slide_dn_y = (f"if(lt(t-{p_s:.3f},0.25),"
                  f"h-{punch_sz+30}+(0.25-(t-{p_s:.3f}))/0.25*80,"
                  f"h-{punch_sz+30})")

    dt_hook = (
        f"drawtext=fontfile={FONT}:text='{hook_txt}':"
        f"fontsize={hook_sz}:fontcolor=#FF3B30:borderw=5:bordercolor=black:"
        f"x=(w-text_w)/2:y='{slide_up_y}':"
        f"enable='between(t,{h_s:.3f},{h_e:.3f})'"
    )
    dt_core = (
        f"drawtext=fontfile={FONT}:text='{core_txt}':"
        f"fontsize={core_sz}:fontcolor=white:borderw=3:bordercolor=black@0.7:"
        f"x=(w-text_w)/2:y=h/2-{core_sz}:"
        f"alpha='{fade_alpha}':"
        f"enable='between(t,{c_s:.3f},{c_e:.3f})'"
    )
    dt_punch = (
        f"drawtext=fontfile={FONT}:text='{punch_txt}':"
        f"fontsize={punch_sz}:fontcolor=#FFD60A:borderw=5:bordercolor=black:"
        f"x=(w-text_w)/2:y='{slide_dn_y}':"
        f"enable='between(t,{p_s:.3f},{p_e:.3f})'"
    )

    vf = f"{dt_hook},{dt_core},{dt_punch}"
    af = f"afade=t=out:st={max(0.0, total - fade):.3f}:d={fade}"

    run(f'ffmpeg -y -i _base.mp4 '
        f'-vf "{vf}" '
        f'-af "{af}" '
        f'-c:v libx264 -pix_fmt yuv420p -crf {crf} -preset fast '
        f'-c:a aac -b:a {abr}k '
        f'output.mp4')


# ═══════════════════════════════════════════════════════════════════════
# ─── MODE CINÉMA ──────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════

def build_cinema_segment(src, seg_out, clip_dur, kb_zoom, opts):
    """Clip normalisé + Ken Burns (zoom lent) via zoompan."""
    W, H = cfg(opts, "resolution").split("x")
    fps  = cfg(opts, "fps")
    crf  = cfg(opts, "crf")
    abr  = cfg(opts, "audio_br")

    scale_crop = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={fps}")

    # Ken Burns : zoom progressif 1 → kb_zoom sur clip_dur
    frames = clip_dur * fps
    inc    = (kb_zoom - 1.0) / max(frames, 1)
    kb_z   = f"min(zoom+{inc:.6f},{kb_zoom})"
    kb_filter = (
        f"zoompan=z='{kb_z}'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d=1:s={W}x{H}:fps={fps}"
    )

    vf = f"{scale_crop},{kb_filter}"

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
        run(f'cp "{seg_paths[0]}" _assembled.mp4', check=False)
        import shutil
        shutil.copy(seg_paths[0], "_assembled.mp4")
        return

    inputs = " ".join(f'-i "{p}"' for p in seg_paths)

    # Durée de chaque segment (pour calculer l'offset xfade)
    durs = [duration(p) for p in seg_paths]

    # Construire la chaîne de filtres xfade
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
    """Applique letterbox + logo + textes cinéma sur _assembled.mp4 → output.mp4."""
    W, H   = cfg(opts, "resolution").split("x")
    lb_h   = cfg(opts, "cinema_lb_h")
    crf    = cfg(opts, "crf")
    abr    = cfg(opts, "audio_br")
    fade   = cfg(opts, "fade_dur")
    Hi     = int(H)
    lb_y_b = Hi - lb_h  # y-pos barre du bas

    total = duration("_assembled.mp4")
    mid_s = total * 0.25
    mid_e = total * 0.72
    fin_s = total * 0.76

    hook_txt  = escape_ffmpeg(texts.get("hook",  "LES CRADOS"))
    core_txt  = escape_ffmpeg(texts.get("core",  "une carte pour chaque horreur"))
    punch_txt = escape_ffmpeg(texts.get("punch", "collectionne si tu oses !"))

    # Barres letterbox
    lb = (f"drawbox=x=0:y=0:w={W}:h={lb_h}:color=black@0.88:t=fill,"
          f"drawbox=x=0:y={lb_y_b}:w={W}:h={lb_h}:color=black@0.88:t=fill")

    # Logo permanent (haut droit)
    # Logo minimaliste (coin bas-droit de la barre haute) — alpha faible
    logo = (f"drawtext=fontfile={FONT}:text='crados.fr':"
            f"fontsize=20:fontcolor=white@0.38:borderw=0:"
            f"x=w-text_w-18:y={lb_h - 22}")

    # Titre/hook (centré, barre haute) — uniquement si hook != branding générique
    _hook_display = hook_txt if hook_txt not in ('LES CRADOS','LES\\ CRADOS') else ''
    title = (f"drawtext=fontfile={FONT}:text='{_hook_display}':"
             f"fontsize=46:fontcolor=white:borderw=3:bordercolor=black:"
             f"x=(w-text_w)/2:y={lb_h//2 - 23}") if _hook_display else ""

    # Sous-titre core (centre, milieu vidéo)
    sub = (f"drawtext=fontfile={FONT}:text='{core_txt}':"
           f"fontsize=38:fontcolor=white@0.92:borderw=2:bordercolor=black@0.8:"
           f"x=(w-text_w)/2:y=h/2-19:"
           f"enable='between(t,{mid_s:.2f},{mid_e:.2f})'")

    # Punch final (barre du bas)
    punch = (f"drawtext=fontfile={FONT}:text='{punch_txt}':"
             f"fontsize=40:fontcolor=#FFD60A:borderw=3:bordercolor=black:"
             f"x=(w-text_w)/2:y={lb_y_b + lb_h//2 - 20}:"
             f"enable='between(t,{fin_s:.2f},{total:.2f})'")

    parts = [lb, logo] + ([title] if title else []) + [sub, punch]
    vf = ",".join(p for p in parts if p)
    af = f"afade=t=out:st={max(0.0, total - fade):.3f}:d={fade}"

    run(f'ffmpeg -y -i _assembled.mp4 '
        f'-vf "{vf}" '
        f'-af "{af}" '
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
    api_key   = ANTHROPIC_KEY

    print("═" * 52)
    print("  ViraCut render.py v5")
    print(f"  Mode    : {mode}  |  Clips : {len(clips_raw)}")
    print(f"  IA      : {'OUI' if api_key else 'NON (secret absent)'}")
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

        print(f"\n[1/5] Segments Ken Burns ({n}×{clip_dur:.1f}s)…")
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
        texts = {
            "hook":  "LES CRADOS",
            "core":  "une carte pour chaque horreur",
            "punch": "collectionne si tu oses !",
        }
        if api_key and descriptions and cfg(opts, "ai_text"):
            result = generate_texts(descriptions, opts)
            if result:
                texts = result
                print(f"  HOOK  : {texts.get('hook')}")
                print(f"  CORE  : {texts.get('core')}")
                print(f"  PUNCH : {texts.get('punch')}")
            else:
                print("  (fallback textes par défaut)")

        # Override custom hook / punch
        if cfg(opts, "custom_hook"):
            texts["hook"] = cfg(opts, "custom_hook")
        if cfg(opts, "custom_punch"):
            texts["punch"] = cfg(opts, "custom_punch")

        print("\n[4/5] Assemblage crossfade…")
        assemble_cinema(seg_paths, xfade, opts)

        print("\n[5/5] Letterbox + logo + overlay final…")
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
            # Respect des rôles manuels
            role_order = {"hook": 0, "core": 1, "punch": 2, "auto": 1}
            ordered = sorted(clips_meta,
                             key=lambda m: role_order.get(m["user_role"], 1))
            # Auto → core par défaut si mélange
            for m in ordered:
                m["role"] = m["user_role"] if m["user_role"] != "auto" else "core"
            # Si un seul clip, il joue le rôle hook
            if len(ordered) == 1:
                ordered[0]["role"] = "hook"

        for m in ordered:
            print(f"  {m.get('role','?'):5s} ← clip {m['index']} "
                  f"(dur={m['duration']:.1f}s "
                  f"hook={m.get('hook_score',0):.1f} "
                  f"punch={m.get('punch_score',0):.1f})")

        print("\n[3/7] Vision IA (Claude) — 3 frames / clip…")
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
        texts = {
            "hook":  cfg(opts, "custom_hook")  or "TAS VU CA",
            "core":  "incroyable mais vrai",
            "punch": cfg(opts, "custom_punch") or "c'etait previsible !",
        }
        if api_key and descriptions and cfg(opts, "ai_text"):
            result = generate_texts(descriptions, opts)
            if result:
                # Custom override
                if cfg(opts, "custom_hook"):
                    result["hook"] = cfg(opts, "custom_hook")
                if cfg(opts, "custom_punch"):
                    result["punch"] = cfg(opts, "custom_punch")
                texts = result
            else:
                print("  (fallback textes par défaut)")
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

        print("\n[6/7] Assemblage + textes animés + audio…")
        build_punch_final(segments, texts, opts)

        print("\n[7/7] output.mp4 généré ✓")

    # Vérification finale
    if os.path.isfile("output.mp4"):
        size = os.path.getsize("output.mp4")
        print(f"\n✅ output.mp4 — {size // 1024} KB")
    else:
        print("\n❌ output.mp4 absent !")
        sys.exit(1)


if __name__ == "__main__":
    start()
