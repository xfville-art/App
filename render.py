"""
render.py — ViraCut Studio v7  ★ LesCrados.Ai Edition ★
═══════════════════════════════════════════════════════
FIX : UnboundLocalError sur hook_sz dans build_cinema_overlay
FIX : Gestion robuste du fallback si solde API Anthropic insuffisant
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
    if not ANTHROPIC_KEY:
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
            time.sleep(2)
    return None


def test_api():
    if not ANTHROPIC_KEY:
        print("  API     : ANTHROPIC_API_KEY absent")
        return False
    result = anthropic_call([{"role": "user", "content": "Dis juste OK"}], max_tokens=10)
    if result and "OK" in result.upper():
        print(f"  API     : OK {ANTHROPIC_MODEL} operationnel")
        return True
    return False


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
    subprocess.run(f'ffmpeg -y -ss {t:.2f} -i "{path}" -vframes 1 -q:v 3 "{out}" 2>/dev/null', shell=True)
    return os.path.isfile(out)


def vision_describe(path, role):
    frames_b64 = []
    for ratio in [0.10, 0.50, 0.85]:
        frame_out = f"_frame_{role}_{int(ratio*100)}.jpg"
        if extract_frame(path, ratio, frame_out):
            with open(frame_out, "rb") as f:
                frames_b64.append(base64.b64encode(f.read()).decode())
    if not frames_b64: return ""

    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}} for b64 in frames_b64]
    content.append({"type": "text", "text": "Decris ce clip video pour TikTok (style Les Crados) en 2 phrases courtes."})

    print(f"    [VISION] Analyse {role}...")
    return anthropic_call([{"role": "user", "content": content}], max_tokens=250) or ""


def generate_texts(descriptions, opts):
    desc_lines = "\n".join(f"[{r.upper()}] {d}" for r, d in descriptions.items() if d).strip()
    if not desc_lines: return None

    custom_hook  = (opts or {}).get("custom_hook", "").strip()
    custom_punch = (opts or {}).get("custom_punch", "").strip()
    
    prompt = (
        f"CONTEXTE VISUEL :\n{desc_lines}\n\n"
        "Genere un JSON pour TikTok (Les Crados) :\n"
        '{"hook":"HOOK MAJUSCULES","core":"action minuscule","punch":"chute minuscule"}'
    )
    if custom_hook: prompt += f"\nHook impose: {custom_hook}"
    if custom_punch: prompt += f"\nPunch impose: {custom_punch}"

    print("    [TEXTES] Generation Claude...")
    raw = anthropic_call([{"role": "user", "content": prompt}], system="JSON ONLY", max_tokens=200)
    if not raw: return None
    try:
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except: return None

# ═══════════════════════════════════════════════════════════════════════
# LOGO SPLASH ANIME
# ═══════════════════════════════════════════════════════════════════════
def build_logo_splash(out, opts):
    W, H  = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps"); crf = cfg(opts, "crf")
    Wi, Hi = int(W), int(H)
    dur   = 5.0
    les_sz, crados_sz, ai_sz = 78, 142, 82
    total_h   = les_sz + 18 + crados_sz + 14 + ai_sz
    block_top = (Hi - total_h) // 2
    les_y, crados_y, ai_y = block_top, block_top + les_sz + 18, block_top + les_sz + 18 + crados_sz + 22

    crad_y_expr = f"if(lt(t,0.8),{Hi},if(lt(t-0.8,0.5),{Hi}+({crados_y}-{Hi})*((t-0.8)/0.5),{crados_y}))"
    ai_y_expr = f"if(lt(t,1.7),{Hi},if(lt(t-1.7,0.4),{Hi}+({ai_y}-{Hi})*((t-1.7)/0.4),{ai_y}))"

    dt_les = f"drawtext=fontfile={FONT}:text='LES':fontsize={les_sz}:fontcolor=white:x=(w-text_w)/2:y={les_y}:enable='gte(t,0.3)'"
    dt_crad = f"drawtext=fontfile={FONT}:text='CRADOS':fontsize={crados_sz}:fontcolor=white:x=(w-text_w)/2:y='{crad_y_expr}':enable='gte(t,0.8)'"
    dt_ai = f"drawtext=fontfile={FONT}:text='.Ai':fontsize={ai_sz}:fontcolor=#FF2442:x=(w-text_w)/2:y='{ai_y_expr}':enable='gte(t,1.7)'"

    vf = f"{dt_les},{dt_crad},{dt_ai},fade=t=in:st=0:d=0.5,fade=t=out:st=4.2:d=0.8"
    run(f'ffmpeg -y -f lavfi -i "color=c=black:size={W}x{H}:rate={fps}" -f lavfi -i "anullsrc=r=44100:cl=stereo" -t {dur} -filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{dur}[a]" -map "[v]" -map "[a]" -c:v libx264 -pix_fmt yuv420p -crf {crf} "{out}"')

def append_logo(premain, opts):
    build_logo_splash("_logo.mp4", opts)
    with open("_concat_logo.txt", "w") as f:
        f.write(f"file '{premain}'\nfile '_logo.mp4'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i _concat_logo.txt -c:v libx264 -pix_fmt yuv420p -crf {cfg(opts, "crf")} output.mp4')

# ═══════════════════════════════════════════════════════════════════════
# MODES RENDU
# ═══════════════════════════════════════════════════════════════════════
def build_cinema_segment(src, seg_out, clip_dur, kb_zoom, opts):
    W, H = cfg(opts, "resolution").split("x"); fps = cfg(opts, "fps")
    scale_crop = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}"
    grade = "eq=saturation=0.9:brightness=-0.02:contrast=1.1"
    inc = (kb_zoom - 1.0) / max(clip_dur * fps, 1)
    kb = f"zoompan=z='min(zoom+{inc:.6f},{kb_zoom})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
    vf = f"{scale_crop},{grade},{kb}"
    if has_audio(src):
        run(f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -vf "{vf}" -c:v libx264 -crf {cfg(opts,"crf")} -c:a aac -shortest "{seg_out}"')
    else:
        run(f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -f lavfi -i "anullsrc" -filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{clip_dur}[a]" -map "[v]" -map "[a]" -c:v libx264 -crf {cfg(opts,"crf")} "{seg_out}"')

def assemble_cinema(seg_paths, xfade_dur, opts):
    if len(seg_paths) == 1:
        run(f'cp "{seg_paths[0]}" _assembled.mp4'); return
    inputs = " ".join(f'-i "{p}"' for p in seg_paths)
    v_parts, a_parts = [], []
    offset = duration(seg_paths[0]) - xfade_dur
    prev_v, prev_a = "[0:v]", "[0:a]"
    for i in range(1, len(seg_paths)):
        nv, na = (f"[xv{i}]", f"[xa{i}]") if i < len(seg_paths)-1 else ("[vfin]", "[afin]")
        v_parts.append(f"{prev_v}[{i}:v]xfade=transition=fade:duration={xfade_dur}:offset={offset}{nv}")
        a_parts.append(f"{prev_a}[{i}:a]acrossfade=d={xfade_dur}{na}")
        offset += duration(seg_paths[i]) - xfade_dur
        prev_v, prev_a = nv, na
    run(f'ffmpeg -y {inputs} -filter_complex "{";".join(v_parts + a_parts)}" -map "[vfin]" -map "[afin]" -c:v libx264 -crf {cfg(opts,"crf")} _assembled.mp4')

def build_cinema_overlay(texts, opts):
    W, H = cfg(opts, "resolution").split("x"); Wi, Hi = int(W), int(H)
    # FIX: Define sizes BEFORE calculating lb positions
    hook_sz, core_sz, punch_sz = 54, 48, 46
    
    lb_top, lb_bot = hook_sz + 16, punch_sz + 16
    lb_y_b = Hi - lb_bot
    total = duration("_assembled.mp4")
    h_e, mid_e = total * 0.20, total * 0.72

    h_txt, c_txt, p_txt = [escape_ffmpeg(texts.get(k, "")) for k in ["hook", "core", "punch"]]
    
    lb = f"drawbox=y=0:h={lb_top}:c=black@0.9:t=fill,drawbox=y={lb_y_b}:h={lb_bot}:c=black@0.9:t=fill"
    dt_h = f"drawbox=y=0:h={lb_top}:c=0xFF2442@0.8:t=fill:enable='lt(t,{h_e})',drawtext=text='{h_txt}':fontsize={hook_sz}:fontcolor=white:x=(w-text_w)/2:y=(({lb_top}-text_h)/2):enable='lt(t,{h_e})'"
    dt_c = f"drawbox=y={Hi*0.65}:h={core_sz+20}:c=black@0.7:t=fill:enable='between(t,{h_e},{mid_e})',drawtext=text='{c_txt}':fontsize={core_sz}:fontcolor=white:x=(w-text_w)/2:y={Hi*0.65+10}:enable='between(t,{h_e},{mid_e})'"
    dt_p = f"drawbox=y={lb_y_b}:h={lb_bot}:c=0xFF6B00@0.9:t=fill:enable='gt(t,{mid_e})',drawtext=text='{p_txt}':fontsize={punch_sz}:fontcolor=white:x=(w-text_w)/2:y={lb_y_b+(lb_bot-text_h)/2}:enable='gt(t,{mid_e})'"

    run(f'ffmpeg -y -i _assembled.mp4 -vf "{lb},{dt_h},{dt_c},{dt_p}" -af "afade=t=out:st={total-0.5}:d=0.5" -c:v libx264 -crf {cfg(opts,"crf")} _premain.mp4')
    append_logo("_premain.mp4", opts)

# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════
def start():
    if not os.path.exists("p.json"): sys.exit(1)
    with open("p.json") as f: data = json.load(f)
    clips_raw = data.get("videos", []); opts = data.get("options", {})
    
    print("=" * 50); print("  ViraCut v7 -- LesCrados.Ai Edition"); print("=" * 50)
    
    raw_paths = []
    for i, v in enumerate(clips_raw):
        p = f"_raw_{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v["data"]))
        raw_paths.append((p, v.get("role", "auto")))

    # Mode Cinema forcé si solde API bas ou auto
    n = len(raw_paths); target = cfg(opts, "cinema_dur"); xf = cfg(opts, "cinema_xfade")
    clip_dur = (target - xf*(n-1)) / n
    
    seg_paths = []
    descriptions = {}
    for i, (src, role) in enumerate(raw_paths):
        out = f"_cin_{i}.mp4"
        build_cinema_segment(src, out, clip_dur, cfg(opts, "cinema_kb_zoom"), opts)
        seg_paths.append(out)
        if cfg(opts, "ai_text"):
            desc = vision_describe(src, f"clip{i}")
            if desc: descriptions[f"clip{i}"] = desc

    fb = pick_fallback(raw_paths[0][0])
    texts = generate_texts(descriptions, opts) or fb
    if cfg(opts, "custom_hook"): texts["hook"] = cfg(opts, "custom_hook")
    if cfg(opts, "custom_punch"): texts["punch"] = cfg(opts, "custom_punch")

    assemble_cinema(seg_paths, xf, opts)
    build_cinema_overlay(texts, opts)
    print("\n DONE: output.mp4")

if __name__ == "__main__":
    start()
