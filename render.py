"""
render.py — ViraCut Les Crados v5
Deux modes automatiques :
  PUNCH  — court viral 7-8s   (flash cuts, colour grading, textes animés)
  CINEMA — long cinématique 26s (Ken Burns, crossfade, logo permanent, letterbox)
Mode auto : cinema si clip > 8s ou 1 seul clip, sinon punch
"""
import json, base64, os, subprocess, urllib.request, time, hashlib, random

# ─────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────
CFG = {
    # ── Partagé ──────────────────────────────────────────────────────
    "mode":       "auto",      # "punch" | "cinema" | "auto"
    "resolution": "720x1280",
    "fps":        24,
    "crf":        18,
    "audio_br":   192,
    "ai_text":    True,
    "custom_hook":  "",
    "custom_punch": "",
    # ── Punch ────────────────────────────────────────────────────────
    "hook_dur":   2.0, "core_dur": 2.5, "punch_dur": 3.0,
    "tolerance":  0.7, "flash_cut": True, "zoom_punch": True,
    "zoom_scale": 1.08, "auto_order": True,
    "fade_dur":   0.3, "scdet_thr": 10,
    "hook_size":  88,  "punch_size": 64, "text_bg": False,
    # ── Cinema ───────────────────────────────────────────────────────
    "cinema_dur":      26.0,  # durée cible totale
    "cinema_clip_min":  7.0,  # secondes min par clip
    "cinema_clip_max": 12.0,  # secondes max par clip
    "cinema_xfade":     0.7,  # durée crossfade
    "cinema_kb_zoom":  1.09,  # zoom final Ken Burns
    "cinema_lb_h":       65,  # hauteur letterbox px
}

FONT    = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────
#  UTILS COMMUNS
# ─────────────────────────────────────────────────────────────────────
def run(cmd, silent=False):
    if not silent: print(f"  ▸ {cmd[:120]}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and not silent:
        print(f"    ✗ {r.stderr[-300:]}")
    return r

def probe(path, fmt="format"):
    r = run(f'ffprobe -v quiet -print_format json -show_{fmt} "{path}"', silent=True)
    try: return json.loads(r.stdout)
    except: return {}

def get_duration(path):
    return float(probe(path)['format']['duration'])

def get_dimensions(path):
    W, H = CFG["resolution"].split("x")
    for s in probe(path, "streams").get('streams', []):
        if s.get('codec_type') == 'video' and s.get('codec_name') != 'mjpeg':
            return int(s['width']), int(s['height'])
    return int(W), int(H)

def dynamic_fontsize(text, base_sz, max_w=None, char_ratio=0.58):
    W = int(CFG["resolution"].split("x")[0])
    lim = max_w or int(W * 0.92)
    est = len(text) * base_sz * char_ratio
    if est > lim:
        return max(32, int(base_sz * lim / est))
    return base_sz

def merge_audio(video, audio_src, out):
    vd = get_duration(video); fd = CFG["fade_dur"] if "fade_dur" in CFG else 0.3
    run(f'ffmpeg -y -i "{video}" -i "{audio_src}" '
        f'-map 0:v -map 1:a -t {vd:.4f} '
        f'-c:v copy -c:a aac -b:a {CFG["audio_br"]}k '
        f'-af "afade=t=out:st={max(0,vd-fd-0.1):.3f}:d={fd}" '
        f'-movflags +faststart "{out}"')

# ─────────────────────────────────────────────────────────────────────
#  ANALYSE (commune)
# ─────────────────────────────────────────────────────────────────────
def get_scene_changes(path):
    thr = CFG["scdet_thr"]
    r = run(f'ffprobe -v quiet -show_frames '
            f'-f lavfi "movie={path},scdet=threshold={thr}" '
            f'-print_format json', silent=True)
    changes = []
    try:
        for fr in json.loads(r.stdout).get('frames', []):
            score = float(fr.get('tags', {}).get('lavfi.scd.score', 0))
            pts   = float(fr.get('pkt_pts_time', fr.get('best_effort_timestamp_time', -1)))
            if score > 0 and pts > 0.2: changes.append((pts, score))
    except: pass
    return sorted(changes)

def get_audio_rms(path):
    r = run(f'ffprobe -v quiet -f lavfi -i "amovie={path},astats=metadata=1:reset=1" '
            f'-show_entries frame_tags=lavfi.astats.Overall.RMS_level -of csv=p=0', silent=True)
    vals = []
    for l in r.stdout.strip().split('\n'):
        try:
            v = float(l)
            if v > -100: vals.append(v)
        except: pass
    return sum(vals)/len(vals) if vals else -60.0

def get_motion_score(path, duration):
    r = run(f'ffprobe -v quiet -f lavfi '
            f'-i "movie={path},fps=4,split[a][b];[a][b]psnr" '
            f'-show_entries frame_tags=lavfi.psnr.mse_avg -of csv=p=0 -t {min(duration,4.0)}', silent=True)
    vals = []
    for l in r.stdout.strip().split('\n'):
        try:
            v = float(l)
            if 0 < v < 9999: vals.append(v)
        except: pass
    return sum(vals)/len(vals) if vals else 0.0

def analyze_clip(path, idx):
    dur     = get_duration(path)
    w, h    = get_dimensions(path)
    changes = get_scene_changes(path)
    rms     = get_audio_rms(path)
    motion  = get_motion_score(path, dur)
    return {
        "path": path, "idx": idx, "duration": dur,
        "width": w, "height": h, "changes": changes,
        "rms": rms, "motion": motion,
        "early": sum(1 for t,s in changes if t <= 2.0),
        "late":  sum(1 for t,s in changes if t >= dur*0.6),
        "peak":  max((s for t,s in changes), default=0),
        "density": len(changes) / max(dur, 0.1),
    }

# ─────────────────────────────────────────────────────────────────────
#  IA (commune)
# ─────────────────────────────────────────────────────────────────────
def extract_frames_b64(path, n=3):
    dur = get_duration(path)
    frames = []
    for i, t in enumerate([dur*0.1, dur*0.5, dur*0.85][:n]):
        out = f"{path}_f{i}.jpg"
        run(f'ffmpeg -y -ss {t:.3f} -i "{path}" -vframes 1 -q:v 2 "{out}"', silent=True)
        if os.path.exists(out):
            with open(out,"rb") as f: frames.append(base64.b64encode(f.read()).decode())
    return frames

def call_claude(messages, max_tokens=500, system=None):
    payload = {"model":"claude-sonnet-4-20250514","max_tokens":max_tokens,"messages":messages}
    if system: payload["system"] = system
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode(),
                headers={"Content-Type":"application/json",
                         "x-api-key": API_KEY,
                         "anthropic-version":"2023-06-01"})
            with urllib.request.urlopen(req, timeout=50) as resp:
                data = json.loads(resp.read())
            return data["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
        except Exception as e:
            print(f"  ⚠ API attempt {attempt+1}: {e}")
            if attempt == 0: time.sleep(2)
    return None

def clean_text(s):
    return (s.replace("'","").replace(":"," ").replace('"',' ')
             .replace(",","").replace("  "," ")
             .encode('ascii','ignore').decode('ascii').strip())

# ═══════════════════════════════════════════════════════════════════════
#  ██████  ██    ██ ███    ██  ██████ ██   ██     MODE
#  ██   ██ ██    ██ ████   ██ ██      ██   ██
#  ██████  ██    ██ ██ ██  ██ ██      ███████
#  ██      ██    ██ ██  ██ ██ ██      ██   ██
#  ██       ██████  ██   ████  ██████ ██   ██
# ═══════════════════════════════════════════════════════════════════════

def score_roles(clips_data):
    n = len(clips_data)
    if n == 1: return [("hook_core_punch", clips_data[0])]
    if n == 2:
        s0 = clips_data[0]["early"]*12 + clips_data[0]["peak"]
        s1 = clips_data[1]["early"]*12 + clips_data[1]["peak"]
        return [("hook", clips_data[0 if s0>=s1 else 1]),
                ("punch", clips_data[1 if s0>=s1 else 0])]
    def hs(c): return c["early"]*12 + c["peak"]*2 + c["motion"]*0.5 - c["duration"]*0.5
    def ps(c): return c["late"]*12  + (c["rms"]+60)*0.8 + c["peak"] - c["density"]*2
    hook_c  = max(clips_data, key=hs)
    rem     = [c for c in clips_data if c["idx"] != hook_c["idx"]]
    punch_c = max(rem, key=ps)
    cores   = [c for c in rem if c["idx"] != punch_c["idx"]]
    result  = [("hook", hook_c)] + [("core", c) for c in cores] + [("punch", punch_c)]
    for role,c in result:
        print(f"  r{c['idx']} → {role.upper():8} motion={c['motion']:.1f} rms={c['rms']:.0f}dB")
    return result

def ai_punch_texts(clips_data, roles_order, custom_hook="", custom_punch=""):
    print("\n  [IA] Génération textes punch...")
    content = []
    SYSTEM = (
        "Tu es le copywriter de Les Crados TikTok — Garbage Pail Kids version francaise. "
        "Humour absurde pince-sans-rire. "
        "REGLES ABSOLUES : zero apostrophe, zero deux-points, zero virgule, zero guillemets."
    )
    for role,clip in roles_order:
        frames = extract_frames_b64(clip["path"])
        if not frames: continue
        content.append({"type":"text","text":f"\n--- Clip {role.upper()} ---"})
        for j,b64 in enumerate(frames):
            content.append({"type":"text","text":f"Frame {['debut','milieu','fin'][j]}:"})
            content.append({"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}})
    c_txt = f"HOOK impose: {custom_hook}" if custom_hook else "Aucune contrainte."
    content.append({"type":"text","text":(
        f"Contraintes: {c_txt}\n\n"
        "Lis les noms sur les cartes et inspire-t-en directement.\n\n"
        "1. HOOK (2-4 mots MAJUSCULES): choc immediat ex: 'ATTENDS QUOI' 'NON MAIS LA' 'JEROME FAIT QUOI'\n"
        "2. CORE_TEXT (3-5 mots ou vide): commentaire pince-sans-rire\n"
        "3. PUNCHLINE (5-8 mots): chute absurde\n\n"
        "JSON strict: {\"hook\":\"TEXTE\",\"core_text\":\"Texte\",\"punchline\":\"Texte\"}"
    )})
    result = call_claude([{"role":"user","content":content}], max_tokens=300, system=SYSTEM)
    if not result: return None
    try:
        d = json.loads(result)
        h = clean_text(custom_hook if custom_hook else d.get("hook",""))
        c = clean_text(d.get("core_text",""))
        p = clean_text(custom_punch if custom_punch else d.get("punchline",""))
        print(f"  ✓ Hook: {h!r}  Core: {c!r}  Punch: {p!r}")
        return h, c, p
    except: return None

def punch_fallback(custom_hook="", custom_punch="", seed=""):
    HOOKS   = ["ATTENDS QUOI","NON MAIS LA","CA EXISTE VRAIMENT","T AS VU CA",
               "MAIS QUI A FAIT CA","REGARDE MOI CA","TROP CRADE","IL EST FOU CE GARS",
               "SCANDALE TOTAL","GAME OVER","WTF ABSOLU","NIVEAU ULTIME","ON EST D ACCORD"]
    PUNCHES = ["Les Crados frappent encore","Y a vraiment pas de mots",
               "Ma mere elle sait pas que je regarde ca","Note de vie 0 sur 10",
               "Certifie degoutant","La honte du quartier",
               "Science sans conscience etc","Quelqu un a valide ca srsly",
               "Chef-d oeuvre ou crime je sais pas","Talent gache au service du chaos",
               "Magistral dans le genre horrible","On lui a rien demande mais bon"]
    CORES   = ["La carte qui tue","Crado certifie","Niveau max atteint","","",""]
    rng = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8],16))
    return (
        custom_hook.replace("'","") if custom_hook else rng.choice(HOOKS),
        rng.choice(CORES),
        custom_punch.replace("'","") if custom_punch else rng.choice(PUNCHES)
    )

# ── PUNCH — Colour grading ──────────────────────────────────────────
def grade_filter(role):
    if role == 'hook':
        return "eq=brightness=0.06:contrast=1.25:saturation=1.65:gamma=0.92,vignette=PI/5"
    elif role == 'core':
        return "eq=brightness=0.02:contrast=1.08:saturation=1.15:gamma_r=0.94,vignette=PI/6"
    else:
        return "eq=brightness=-0.04:contrast=1.18:saturation=0.72:gamma=1.05:gamma_b=0.90,vignette=PI/3"

def make_vf(src_w, src_h):
    W, H = [int(x) for x in CFG["resolution"].split("x")]
    fps  = CFG["fps"]
    if src_w/src_h <= W/H + 0.05:
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}"
    sh = int(src_h * W / src_w); sh -= sh % 2
    return f"scale={W}:{sh},pad={W}:{H}:0:{(H-sh)//2}:black,setsar=1,fps={fps}"

def make_flash(color="white", name="flash.mp4"):
    W, H = [int(x) for x in CFG["resolution"].split("x")]
    run(f'ffmpeg -y -f lavfi -i "color=c={color}:size={W}x{H}:rate={CFG["fps"]}" '
        f'-t 0.042 -vf "setsar=1" -c:v libx264 -pix_fmt yuv420p "{name}"', silent=True)

def best_cut(changes, target, dur):
    window = [(t,s) for t,s in changes if abs(t-target) <= CFG["tolerance"]]
    if window:
        best = max(window, key=lambda x: x[1])
        print(f"  ✓ Cut naturel {best[0]:.3f}s (score {best[1]:.1f})")
        return best[0]
    safe = min(target, dur - 0.15)
    print(f"  ≈ Coupe forcee {safe:.3f}s"); return safe

def trim_segment(src, out, duration, vf, role='core'):
    full_vf = f"{vf},{grade_filter(role)}"
    r = run(f'ffmpeg -y -i "{src}" -t {duration:.4f} -vf "{full_vf}" '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print(f"  ⚠ Grade echoue — fallback sans grade")
        run(f'ffmpeg -y -i "{src}" -t {duration:.4f} -vf "{vf}" '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')

def apply_zoom_punch(src, out, punch_t):
    fps = CFG["fps"]; scale = CFG["zoom_scale"]
    pf  = int(punch_t * fps); zi, zo = 3, 8
    W, H = [int(x) for x in CFG["resolution"].split("x")]
    ze  = (f"if(between(on,{pf},{pf+zi}),1.0+(on-{pf})*{scale-1:.3f}/{zi},"
           f"if(between(on,{pf+zi},{pf+zi+zo}),{scale:.3f}-({scale-1:.3f})*(on-{pf+zi})/{zo},1.0))")
    r   = run(f'ffmpeg -y -i "{src}" '
              f'-vf "zoompan=z=\'{ze}\':x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':d=1:s={W}x{H}:fps={fps}" '
              f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        run(f'cp "{src}" "{out}"', silent=True)

def concat_segments(segments, out):
    with open("list.txt","w") as f:
        [f.write(f"file '{s}'\n") for s in segments]
    run(f'ffmpeg -y -f concat -safe 0 -i list.txt '
        f'-c:v libx264 -crf {CFG["crf"]} -preset fast '
        f'-pix_fmt yuv420p -movflags +faststart -an "{out}"')

# ── PUNCH — Textes animés ───────────────────────────────────────────
def write_punch_text_filter(hook, core_text, punchline, total_dur):
    W, H = [int(x) for x in CFG["resolution"].split("x")]
    h_sz = dynamic_fontsize(hook,      CFG["hook_size"],  int(W*0.92))
    p_sz = dynamic_fontsize(punchline, CFG["punch_size"], int(W*0.92))
    c_sz = dynamic_fontsize(core_text, max(48, CFG["punch_size"]-10), int(W*0.88)) if core_text else 48
    def ft(t): return f"{t:.3f}"
    hook_y = 115; pl_y = H - 145 - p_sz; core_y = H//2 - c_sz//2
    h_pop=0.15; h_hold=2.0; h_out=2.5
    ci=2.6; cs=2.85; ch=min(4.8,total_dur-2.6); co=min(5.1,total_dur-2.3)
    pi=max(0.0,total_dur-2.8); pb=pi+0.20; psh=max(pb,total_dur-0.55); po=total_dur
    # Hook
    h_y     = f"if(lt(t\\,{ft(h_pop)})\\,{hook_y-50}+(t/{ft(max(h_pop,0.01))})*50\\,{hook_y})"
    h_alpha = (f"if(lt(t\\,{ft(h_pop)})\\,t/{ft(max(h_pop,0.01))}\\,"
               f"if(lt(t\\,{ft(h_hold)})\\,1\\,max(0\\,({ft(h_out)}-t)/{ft(max(h_out-h_hold,0.01))})))")
    hook_f  = (f"drawtext=text='{hook}':fontfile={FONT}:fontsize={h_sz}:"
               f"fontcolor=#FF2D55:borderw=10:bordercolor=black@0.9:"
               f"shadowx=5:shadowy=5:shadowcolor=black@0.8:"
               f"x=(w-text_w)/2:y={h_y}:alpha='{h_alpha}':enable='between(t\\,0\\,{ft(h_out)})'")
    # Core
    core_f = ""
    if core_text:
        c_alpha = (f"if(lt(t\\,{ft(cs)})\\,(t-{ft(ci)})/{ft(max(cs-ci,0.01))}\\,"
                   f"if(lt(t\\,{ft(ch)})\\,0.95\\,max(0\\,({ft(co)}-t)/{ft(max(co-ch,0.01))})))")
        c_x = (f"if(lt(t\\,{ft(cs)})\\,"
               f"w-(t-{ft(ci)})*w/{ft(max(cs-ci,0.01))}+(w-text_w)/2\\,(w-text_w)/2)")
        core_f = (f",drawtext=text='{core_text}':fontfile={FONT}:fontsize={c_sz}:"
                  f"fontcolor=white:borderw=7:bordercolor=black:"
                  f"shadowx=4:shadowy=4:shadowcolor=black@0.9:"
                  f"x={c_x}:y={core_y}:alpha='{c_alpha}':enable='between(t\\,{ft(ci)}\\,{ft(co)})'")
    # Punchline
    pl_y_e  = (f"if(lt(t\\,{ft(pb)})\\,{pl_y+90}-(t-{ft(pi)})*110/{ft(max(pb-pi,0.01))}\\,"
               f"if(lt(t\\,{ft(pb+0.1)})\\,{pl_y-20}+(t-{ft(pb)})*20/{ft(0.1)}\\,{pl_y}))")
    pl_x    = f"if(lt(t\\,{ft(psh)})\\,(w-text_w)/2\\,(w-text_w)/2+10*sin((t-{ft(psh)})*70))"
    pl_alpha= (f"if(lt(t\\,{ft(pb)})\\,(t-{ft(pi)})/{ft(max(pb-pi,0.01))}\\,"
               f"if(lt(t\\,{ft(po-0.2)})\\,1\\,max(0\\,({ft(po)}-t)/0.2)))")
    pl_f    = (f",drawtext=text='{punchline}':fontfile={FONT}:fontsize={p_sz}:"
               f"fontcolor=#FFE600:borderw=9:bordercolor=black:"
               f"shadowx=5:shadowy=5:shadowcolor=black@0.9:"
               f"x={pl_x}:y={pl_y_e}:alpha='{pl_alpha}':enable='between(t\\,{ft(pi)}\\,{ft(po)})'")
    with open("text_filter.txt","w",encoding="utf-8") as f:
        f.write(hook_f + core_f + pl_f)

def apply_text_overlay_punch(src, out, hook, core_text, punchline):
    write_punch_text_filter(hook, core_text, punchline, get_duration(src))
    r = run(f'ffmpeg -y -i "{src}" -filter_script:v text_filter.txt '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print("  ⚠ drawtext echoue — copie sans texte")
        run(f'cp "{src}" "{out}"', silent=True)

# ─────────────────────────────────────────────────────────────────────
#  PUNCH — Pipeline complet
# ─────────────────────────────────────────────────────────────────────
def render_punch(clips_data, videos_meta):
    print("\n── MODE PUNCH ──────────────────────────────────────────")
    # Ordre narratif
    manual_roles = {v.get('role','auto') for v in videos_meta}
    if CFG["auto_order"] and manual_roles == {'auto'}:
        roles_order = score_roles(clips_data)
    else:
        role_map = {'hook':'hook','core':'core','punch':'punch','auto':None}
        roles_order = []
        for i,v in enumerate(videos_meta):
            r = role_map.get(v.get('role','auto')) or ['hook','core','punch'][min(i,2)]
            roles_order.append((r, clips_data[i]))
        print("  → Ordre manuel")

    durations = []
    for role,_ in roles_order:
        if 'hook_core_punch' in role: durations.append(CFG["hook_dur"]+CFG["core_dur"]+CFG["punch_dur"])
        elif role=='hook': durations.append(CFG["hook_dur"])
        elif role=='core': durations.append(CFG["core_dur"])
        else:              durations.append(CFG["punch_dur"])

    # Textes IA ou fallback
    print(f"\n[IA] Textes punch...")
    hook_text = core_text = punch_text = ""
    if CFG["ai_text"] and API_KEY:
        res = ai_punch_texts(clips_data, roles_order, CFG.get("custom_hook",""), CFG.get("custom_punch",""))
        if res: hook_text, core_text, punch_text = res
    if not hook_text:
        if not API_KEY: print("  ⚠ Pas d API key — fallback Les Crados")
        seed = "".join(cd["path"] for cd in clips_data)
        hook_text, core_text, punch_text = punch_fallback(
            CFG.get("custom_hook",""), CFG.get("custom_punch",""), seed=seed)
        print(f"  → {hook_text!r} | {core_text!r} | {punch_text!r}")

    # Flash colorés
    FLASH_COLORS = {'hook':'white','core':'orange','punch':'0x8B0000'}
    if CFG["flash_cut"]:
        for rn,col in FLASH_COLORS.items(): make_flash(col, f"flash_{rn}.mp4")

    # Découpe + effets + grading
    segments = []
    for i, ((role, clip), target) in enumerate(zip(roles_order, durations)):
        path=clip["path"]; changes=clip["changes"]; dur=clip["duration"]; w,h=clip["width"],clip["height"]
        cut_t   = best_cut(changes, target, dur)
        raw_seg = f"raw_seg{i}.mp4"
        trim_segment(path, raw_seg, cut_t, make_vf(w, h), role=role)
        seg_out = f"seg{i}.mp4"
        if CFG["zoom_punch"] and role in ('core','hook_core_punch'):
            in_seg = [(t,s) for t,s in changes if 0.3 < t < cut_t]
            if in_seg:
                mid = cut_t/2
                pt  = max(in_seg, key=lambda x: x[1]*(1-abs(x[0]-mid)/max(mid,0.1)))
                print(f"  → Zoom punch à {pt[0]:.3f}s")
                apply_zoom_punch(raw_seg, seg_out, pt[0])
            else: run(f'cp "{raw_seg}" "{seg_out}"', silent=True)
        else: run(f'cp "{raw_seg}" "{seg_out}"', silent=True)
        segments.append(seg_out)
        print(f"  ✓ seg{i} ({role}) → {get_duration(seg_out):.3f}s")

    # Assemblage avec flash colorés
    interleaved = []
    for i,seg in enumerate(segments):
        interleaved.append(seg)
        if i < len(segments)-1 and CFG["flash_cut"]:
            next_role = roles_order[i+1][0]
            ff = f"flash_{next_role}.mp4"
            if os.path.exists(ff): interleaved.append(ff)
    concat_segments(interleaved, "no_text.mp4")

    # Textes
    print(f"  Overlay: {hook_text!r} | {core_text!r} | {punch_text!r}")
    apply_text_overlay_punch("no_text.mp4", "no_audio.mp4", hook_text, core_text, punch_text)

    return hook_text, punch_text

# ═══════════════════════════════════════════════════════════════════════
#   ██████ ██ ███    ██ ███████ ███    ███  █████      MODE
#  ██      ██ ████   ██ ██      ████  ████ ██   ██
#  ██      ██ ██ ██  ██ █████   ██ ████ ██ ███████
#  ██      ██ ██  ██ ██ ██      ██  ██  ██ ██   ██
#   ██████ ██ ██   ████ ███████ ██      ██ ██   ██
# ═══════════════════════════════════════════════════════════════════════

def ai_cinema_texts(clips_data, custom_hook="", custom_punch=""):
    print("\n  [IA] Génération textes cinéma...")
    content = []
    SYSTEM = (
        "Tu es le copywriter de Les Crados TikTok. "
        "Style cinema TikTok : accroches mystere et nostalgie. "
        "REGLES ABSOLUES : zero apostrophe, zero deux-points, zero virgule, zero guillemets. "
        "Lis les noms et themes visuels sur les cartes et utilise-les directement."
    )
    for i,cd in enumerate(clips_data[:3]):  # max 3 clips analysés
        frames = extract_frames_b64(cd["path"])
        if not frames: continue
        content.append({"type":"text","text":f"\n--- Clip {i+1} ---"})
        for j,b64 in enumerate(frames):
            content.append({"type":"text","text":f"Frame {['debut','milieu','fin'][j]}:"})
            content.append({"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}})

    ch_txt = f"HOOK impose: {custom_hook}" if custom_hook else "Aucune contrainte."
    content.append({"type":"text","text":(
        f"Contraintes: {ch_txt}\n\n"
        "Genere 5 textes pour une video TikTok CINEMA des Crados (26s).\n\n"
        "1. HOOK_LINE (3-5 mots MAJUSCULES): accroche alerte ex: 'NE REGARDE PAS CA' "
        "'TU VEUX PAS VOIR CA' 'ATTENDS LA FIN' 'NE SWIPE PAS ENCORE'\n\n"
        "2. SUB_HOOK (5-9 mots, parentheses incluses): sous-titre du hook "
        "ex: '(Si tu es nostalgique)' '(Si tu aimes les Crados)' '(Si tu connais ca)'\n\n"
        "3. SWIPE_LINE (3-5 mots MAJUSCULES): avertissement milieu de video "
        "ex: 'NE SWIPE PAS' 'RESTE ENCORE' 'ATTENDS LA SUITE'\n\n"
        "4. SUB_SWIPE (4-8 mots, parentheses incluses): contexte du swipe warning "
        "ex: '(Si tu aimes le Steampunk)' '(Si tu connais ce perso)' '(Si tu aimes les Crados)'\n\n"
        "5. GHOST_QUESTION (3-5 mots MAJUSCULES): grande question semi-transparente fin de video "
        "ex: 'HEROS OU MONSTRE' 'GENIE OU FOLIE' 'ART OU HORREUR' 'BEAU OU DEGOUTANT'\n\n"
        "JSON strict sans markdown:\n"
        "{\"hook_line\":\"\",\"sub_hook\":\"\",\"swipe_line\":\"\","
        "\"sub_swipe\":\"\",\"ghost_question\":\"\"}"
    )})
    result = call_claude([{"role":"user","content":content}], max_tokens=400, system=SYSTEM)
    if not result: return None
    try:
        d = json.loads(result)
        out = {k: clean_text(d.get(k,"")) for k in
               ["hook_line","sub_hook","swipe_line","sub_swipe","ghost_question"]}
        for k,v in out.items(): print(f"  ✓ {k:16}: {v!r}")
        return out
    except Exception as e:
        print(f"  ⚠ Parse echoue ({e})"); return None

def cinema_fallback(seed=""):
    HOOKS   = ["NE REGARDE PAS CA","NE SWIPE PAS","TU VEUX PAS VOIR CA",
               "ATTENDS LA FIN","REGARDE JUSQU AU BOUT","ILS EXISTENT VRAIMENT"]
    SUBS    = ["(Si tu es nostalgique)","(Si tu aimes les Crados)",
               "(Si tu connais ces cartes)","(Si tu as le coeur fragile)",
               "(Si tu aimes les monstres)","(Si tu sais qui c est)"]
    SWIPES  = ["NE SWIPE PAS","RESTE ENCORE","ATTENDS LA SUITE",
               "TU VAS REGRETTER","UN DE PLUS"]
    SSUBS   = ["(Si tu aimes ca)","(Si tu connais ce perso)",
               "(Ca devient interessant)","(La meilleure carte)","(Regarde bien)"]
    GHOSTS  = ["HEROS OU MONSTRE","GENIE OU FOLIE","ART OU HORREUR",
               "BEAU OU DEGOUTANT","CHEF D OEUVRE","CRADO CERTIFIE"]
    rng = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8],16))
    return {
        "hook_line":      rng.choice(HOOKS),
        "sub_hook":       rng.choice(SUBS),
        "swipe_line":     rng.choice(SWIPES),
        "sub_swipe":      rng.choice(SSUBS),
        "ghost_question": rng.choice(GHOSTS),
    }

def apply_ken_burns(src, out, duration, direction=0):
    """
    Ken Burns : zoom lent 1.0 → cinema_kb_zoom + pan directionnel doux.
    direction 0=centre 1=gauche-droite 2=droite-gauche 3=bas-haut
    """
    W, H     = [int(x) for x in CFG["resolution"].split("x")]
    fps      = CFG["fps"]
    zoom_end = CFG["cinema_kb_zoom"]
    n_frames = int(duration * fps)
    zoom_step= (zoom_end - 1.0) / max(n_frames, 1)

    z_expr = f"min(zoom+{zoom_step:.6f},{zoom_end:.4f})"
    # Expressions de pan (centré + dérive douce)
    if direction == 1:
        x_expr = f"iw/2-(iw/zoom/2)+on*{int(W*0.03/max(n_frames,1))}"
    elif direction == 2:
        x_expr = f"iw/2-(iw/zoom/2)-on*{int(W*0.03/max(n_frames,1))}"
    else:
        x_expr = "iw/2-(iw/zoom/2)"

    if direction == 3:
        y_expr = f"ih/2-(ih/zoom/2)-on*{int(H*0.02/max(n_frames,1))}"
    else:
        y_expr = "ih/2-(ih/zoom/2)"

    # Recadrage + Ken Burns
    base_vf = make_vf(*get_dimensions(src))
    kb_vf   = f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={n_frames}:s={W}x{H}:fps={fps}"
    full_vf = f"{base_vf},{kb_vf}"

    r = run(f'ffmpeg -y -i "{src}" -t {duration:.4f} -vf "{full_vf}" '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print("  ⚠ Ken Burns echoue — fallback sans KB")
        run(f'ffmpeg -y -i "{src}" -t {duration:.4f} -vf "{base_vf}" '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')

def xfade_clips(clips, out):
    """Crossfade enchaîné entre tous les clips."""
    xd = CFG["cinema_xfade"]
    if len(clips) == 1:
        run(f'cp "{clips[0]}" "{out}"', silent=True); return
    durations = [get_duration(c) for c in clips]
    inputs    = " ".join(f'-i "{c}"' for c in clips)
    if len(clips) == 2:
        offset = max(0.1, durations[0] - xd)
        fc = (f"[0:v][1:v]xfade=transition=fade:duration={xd:.2f}"
              f":offset={offset:.3f}[vout]")
    else:
        parts  = []; prev = "[0:v]"; offset = max(0.1, durations[0] - xd)
        for i in range(1, len(clips)):
            lbl = f"[v{i}]" if i < len(clips)-1 else "[vout]"
            parts.append(f"{prev}[{i}:v]xfade=transition=fade:duration={xd:.2f}:offset={offset:.3f}{lbl}")
            prev = lbl
            if i < len(clips)-1: offset += max(0.1, durations[i] - xd)
        fc = ";".join(parts)
    r = run(f'ffmpeg -y {inputs} -filter_complex "{fc}" -map "[vout]" '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print("  ⚠ xfade echoue — fallback concat")
        concat_segments(clips, out)

def write_cinema_text_filter(texts, total_dur):
    """
    Textes cinéma :
    - Letterbox haut/bas (noir permanent)
    - Logo LES CRADOS argenté top-right (permanent)
    - Hook alerte avec icône [!] jaune (0 → 5.5s)
    - Swipe warning avec icône [!] (30% → 60% de la durée)
    - Question fantôme semi-transparente (60% → fin-1s)
    """
    W, H  = [int(x) for x in CFG["resolution"].split("x")]
    lb_h  = CFG["cinema_lb_h"]  # 65px letterbox
    def ft(t): return f"{t:.3f}"
    def dsz(txt, base, maxw=None): return dynamic_fontsize(txt, base, maxw or int(W*0.85))

    hook_line      = texts.get("hook_line","NE REGARDE PAS CA")
    sub_hook       = texts.get("sub_hook","(Si tu aimes les Crados)")
    swipe_line     = texts.get("swipe_line","NE SWIPE PAS")
    sub_swipe      = texts.get("sub_swipe","(Si tu connais ce perso)")
    ghost_question = texts.get("ghost_question","HEROS OU MONSTRE")

    # ── TIMINGS ───────────────────────────────────────────────────────
    h_in  = 0.0;   h_out = 5.5;  h_fade = 0.4
    sw_in = total_dur * 0.28;  sw_out = total_dur * 0.62;  sw_fade = 0.4
    g_in  = total_dur * 0.60;  g_out  = total_dur - 1.2;   g_fade  = 1.2

    # ── LETTERBOX ─────────────────────────────────────────────────────
    lb_top = f"drawbox=x=0:y=0:w=iw:h={lb_h}:color=black@1.0:t=fill"
    lb_bot = f"drawbox=x=0:y=ih-{lb_h}:w=iw:h={lb_h}:color=black@1.0:t=fill"

    # ── LOGO LES CRADOS (argenté, top-right, permanent) ───────────────
    # On place le logo DANS la letterbox du haut
    logo_y1  = 6
    logo_y2  = logo_y1 + 32
    logo_y3  = logo_y2 + 30
    logo_les = (f"drawtext=text='LES':fontfile={FONT}:fontsize=36:"
                f"fontcolor=0xD0D0D0:borderw=2:bordercolor=black:"
                f"shadowx=2:shadowy=2:shadowcolor=black:"
                f"x=w-text_w-16:y={logo_y1}")
    logo_cra = (f"drawtext=text='CRADOS':fontfile={FONT}:fontsize=40:"
                f"fontcolor=0xD0D0D0:borderw=2:bordercolor=black:"
                f"shadowx=2:shadowy=2:shadowcolor=black:"
                f"x=w-text_w-16:y={logo_y2}")
    logo_url = (f"drawtext=text='lescrados.ai':fontfile={FONT}:fontsize=16:"
                f"fontcolor=0x909090:borderw=1:bordercolor=black:"
                f"x=w-text_w-16:y={logo_y3}")

    # ── HOOK BLOCK (0 → 5.5s) ────────────────────────────────────────
    # Zone : juste sous la letterbox du haut
    h_sz   = dsz(hook_line, 60, int(W * 0.82))
    sh_sz  = dsz(sub_hook,  32, int(W * 0.88))
    icon_y = lb_h + 18
    hook_y = icon_y - 6
    sub_y  = hook_y + h_sz + 10

    h_alpha = (f"if(lt(t\\,{ft(h_in+h_fade)})\\,(t-{ft(h_in)})/{ft(h_fade)}\\,"
               f"if(lt(t\\,{ft(h_out-h_fade)})\\,1\\,"
               f"max(0\\,({ft(h_out)}-t)/{ft(h_fade)})))")

    # Carré jaune [!] à gauche
    icon_box = (f"drawbox=x=16:y={icon_y}:w=50:h=50:color=0xFFCC00@1.0:t=fill:"
                f"enable='between(t\\,{ft(h_in)}\\,{ft(h_out)})'")
    icon_txt = (f"drawtext=text='!':fontfile={FONT}:fontsize=40:fontcolor=black:"
                f"x=31:y={icon_y+2}:enable='between(t\\,{ft(h_in)}\\,{ft(h_out)})'")

    hook_f  = (f"drawtext=text='{hook_line}':fontfile={FONT}:fontsize={h_sz}:"
               f"fontcolor=white:borderw=8:bordercolor=black:"
               f"shadowx=4:shadowy=4:shadowcolor=black:"
               f"x=76:y={hook_y}:alpha='{h_alpha}':"
               f"enable='between(t\\,{ft(h_in)}\\,{ft(h_out)})'")
    sub_f   = (f"drawtext=text='{sub_hook}':fontfile={FONT}:fontsize={sh_sz}:"
               f"fontcolor=white@0.92:borderw=4:bordercolor=black:"
               f"x=(w-text_w)/2:y={sub_y}:alpha='{h_alpha}':"
               f"enable='between(t\\,{ft(h_in)}\\,{ft(h_out)})'")

    # ── SWIPE WARNING (30% → 60%) ─────────────────────────────────────
    sw_sz   = dsz(swipe_line, 56, int(W * 0.82))
    ssw_sz  = dsz(sub_swipe,  30, int(W * 0.88))
    sw_y    = H // 2 - sw_sz - 10
    ssw_y   = sw_y + sw_sz + 12

    sw_alpha = (f"if(lt(t\\,{ft(sw_in+sw_fade)})\\,(t-{ft(sw_in)})/{ft(sw_fade)}\\,"
                f"if(lt(t\\,{ft(sw_out-sw_fade)})\\,1\\,"
                f"max(0\\,({ft(sw_out)}-t)/{ft(sw_fade)})))")

    sw_icon_box = (f"drawbox=x=16:y={sw_y}:w=44:h=44:color=0xFFCC00@1.0:t=fill:"
                   f"enable='between(t\\,{ft(sw_in)}\\,{ft(sw_out)})'")
    sw_icon_txt = (f"drawtext=text='!':fontfile={FONT}:fontsize=34:fontcolor=black:"
                   f"x=29:y={sw_y+2}:enable='between(t\\,{ft(sw_in)}\\,{ft(sw_out)})'")
    sw_f        = (f"drawtext=text='{swipe_line}':fontfile={FONT}:fontsize={sw_sz}:"
                   f"fontcolor=white:borderw=7:bordercolor=black:"
                   f"shadowx=3:shadowy=3:shadowcolor=black:"
                   f"x=70:y={sw_y}:alpha='{sw_alpha}':"
                   f"enable='between(t\\,{ft(sw_in)}\\,{ft(sw_out)})'")
    ssw_f       = (f"drawtext=text='{sub_swipe}':fontfile={FONT}:fontsize={ssw_sz}:"
                   f"fontcolor=white@0.9:borderw=4:bordercolor=black:"
                   f"x=(w-text_w)/2:y={ssw_y}:alpha='{sw_alpha}':"
                   f"enable='between(t\\,{ft(sw_in)}\\,{ft(sw_out)})'")

    # ── GHOST QUESTION (grand, semi-transparent, fondu lent) ──────────
    g_sz    = dsz(ghost_question, 82)
    g_y     = int(H * 0.57)
    g_alpha = (f"if(lt(t\\,{ft(g_in+g_fade)})\\,(t-{ft(g_in)})/{ft(g_fade)}*0.22\\,"
               f"if(lt(t\\,{ft(g_out-0.6)})\\,0.22\\,"
               f"max(0\\,({ft(g_out)}-t)/0.6)*0.22))")
    ghost_f = (f"drawtext=text='{ghost_question}':fontfile={FONT}:fontsize={g_sz}:"
               f"fontcolor=white:borderw=5:bordercolor=black@0.2:"
               f"x=(w-text_w)/2:y={g_y}:alpha='{g_alpha}':"
               f"enable='between(t\\,{ft(g_in)}\\,{ft(g_out)})'")

    # Assemblage
    parts = [
        lb_top, lb_bot,
        logo_les, logo_cra, logo_url,
        icon_box, icon_txt,
        hook_f,   sub_f,
        sw_icon_box, sw_icon_txt,
        sw_f,     ssw_f,
        ghost_f
    ]
    with open("cinema_filter.txt","w",encoding="utf-8") as f:
        f.write(",".join(parts))

def apply_cinema_text_overlay(src, out, texts):
    total_dur = get_duration(src)
    write_cinema_text_filter(texts, total_dur)
    r = run(f'ffmpeg -y -i "{src}" -filter_script:v cinema_filter.txt '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print("  ⚠ cinema drawtext echoue — copie sans texte")
        run(f'cp "{src}" "{out}"', silent=True)

# ─────────────────────────────────────────────────────────────────────
#  CINEMA — Pipeline complet
# ─────────────────────────────────────────────────────────────────────
def render_cinema(clips_data):
    print("\n── MODE CINEMA ─────────────────────────────────────────")
    n    = len(clips_data)
    # Durée par clip : répartir cinema_dur équitablement
    target_total = CFG["cinema_dur"]
    xd           = CFG["cinema_xfade"]
    clip_dur     = max(CFG["cinema_clip_min"],
                       min(CFG["cinema_clip_max"],
                           (target_total + (n-1)*xd) / n))
    print(f"  {n} clip(s) × {clip_dur:.1f}s = ~{n*clip_dur-(n-1)*xd:.1f}s total")

    # Ken Burns par clip (directions alternées pour variété)
    DIRECTIONS = [0, 1, 2, 3]
    kb_clips = []
    for i, cd in enumerate(clips_data):
        direction = DIRECTIONS[i % len(DIRECTIONS)]
        kb_out    = f"kb_{i}.mp4"
        raw_dur   = cd["duration"]
        use_dur   = min(clip_dur, raw_dur) if raw_dur >= 3.0 else clip_dur
        print(f"\n  Clip {i} → Ken Burns (direction {direction}) {use_dur:.1f}s")
        # Si clip trop court, on le loope
        if raw_dur < use_dur - 0.2:
            looped = f"looped_{i}.mp4"
            loops  = int(use_dur / raw_dur) + 2
            run(f'ffmpeg -y -stream_loop {loops} -i "{cd["path"]}" -t {use_dur:.4f} '
                f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{looped}"')
            apply_ken_burns(looped, kb_out, use_dur, direction)
        else:
            apply_ken_burns(cd["path"], kb_out, use_dur, direction)
        if os.path.exists(kb_out):
            kb_clips.append(kb_out)
            print(f"  ✓ kb_{i}.mp4 → {get_duration(kb_out):.2f}s")

    if not kb_clips:
        print("  ✗ Aucun clip Ken Burns — abandon"); return None, None

    # Crossfade entre clips
    print(f"\n  Crossfade {len(kb_clips)} clips (xfade={xd}s)...")
    xfade_clips(kb_clips, "base_cinema.mp4")
    real_dur = get_duration("base_cinema.mp4")
    print(f"  ✓ base_cinema.mp4 → {real_dur:.2f}s")

    # Textes IA ou fallback
    print(f"\n[IA] Textes cinéma...")
    texts = None
    if CFG["ai_text"] and API_KEY:
        texts = ai_cinema_texts(clips_data, CFG.get("custom_hook",""))
    if not texts:
        if not API_KEY: print("  ⚠ Pas d API key — fallback cinéma")
        seed  = "".join(cd["path"] for cd in clips_data)
        texts = cinema_fallback(seed)
        for k,v in texts.items(): print(f"  → {k:16}: {v!r}")

    # Overlay textes
    print(f"\n  Overlay cinéma...")
    apply_cinema_text_overlay("base_cinema.mp4", "no_audio.mp4", texts)

    return texts.get("hook_line",""), texts.get("ghost_question","")

# ─────────────────────────────────────────────────────────────────────
#  DÉTECTION MODE AUTO
# ─────────────────────────────────────────────────────────────────────
def detect_mode(clips_data, explicit_mode="auto"):
    if explicit_mode in ("punch","cinema"):
        print(f"  Mode explicite : {explicit_mode.upper()}")
        return explicit_mode
    # Auto : cinema si un clip > 8s OU si 1 seul clip
    max_dur = max(cd["duration"] for cd in clips_data)
    if len(clips_data) == 1 or max_dur > 8.0:
        print(f"  Mode auto → CINEMA (max_dur={max_dur:.1f}s, n={len(clips_data)})")
        return "cinema"
    print(f"  Mode auto → PUNCH (max_dur={max_dur:.1f}s, n={len(clips_data)})")
    return "punch"

# ─────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────
def start():
    if not os.path.exists('p.json'):
        print("✗ p.json introuvable"); return
    with open('p.json') as f: data = json.load(f)
    opts = data.get('options', {})
    for k,v in opts.items():
        if k in CFG: CFG[k] = v
    print(f"▶ ViraCut Les Crados v5 — {CFG['resolution']} {CFG['fps']}fps")

    videos = data.get('videos', [])
    print(f"\n[1] Extraction de {len(videos)} clip(s)")
    clips_data = []
    for i,v in enumerate(videos):
        path = f"r{i}.mp4"
        with open(path,"wb") as fout: fout.write(base64.b64decode(v['data']))
        print(f"\n  Clip r{i}...")
        cd = analyze_clip(path, i)
        print(f"  → {cd['duration']:.2f}s  {cd['width']}x{cd['height']}  "
              f"changes={len(cd['changes'])}  motion={cd['motion']:.1f}  rms={cd['rms']:.0f}dB")
        clips_data.append(cd)

    print(f"\n[2] Détection mode")
    mode = detect_mode(clips_data, CFG.get("mode","auto"))

    if mode == "cinema":
        result = render_cinema(clips_data)
        if result is None: return
        h_text, g_text = result
    else:
        h_text, p_text = render_punch(clips_data, data.get('videos',[]))

    # Audio
    print(f"\n[Final] Audio...")
    audio_clip = None
    for cd in clips_data:
        if run(f'ffprobe -v quiet -select_streams a -show_streams "{cd["path"]}"',
               silent=True).stdout.strip():
            audio_clip = cd["path"]; break
    if audio_clip: merge_audio("no_audio.mp4", audio_clip, "output.mp4")
    else: os.rename("no_audio.mp4", "output.mp4")

    if os.path.exists("output.mp4"):
        fd = get_duration("output.mp4"); fw,fh = get_dimensions("output.mp4")
        print(f"\n{'='*52}")
        print(f"✅ SUCCES  {fw}x{fh}  {fd:.2f}s  MODE={mode.upper()}")
        print(f"{'='*52}")
    else:
        print("\n❌ ECHEC : output.mp4 non genere")

if __name__ == "__main__":
    start()
