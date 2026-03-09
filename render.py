"""
render.py — ViraCut Les Crados v4
Pipeline : extraction → analyse → IA (vision + textes) → montage → textes viraux
"""
import json, base64, os, subprocess, urllib.request, time, hashlib, random

# ─────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "hook_dur": 2.0, "core_dur": 2.5, "punch_dur": 3.0,
    "tolerance": 0.7, "flash_cut": True, "zoom_punch": True,
    "zoom_scale": 1.08, "ai_text": True, "auto_order": True,
    "custom_hook": "", "custom_punch": "",
    "resolution": "720x1280", "fps": 24, "crf": 18,
    "audio_br": 192, "fade_dur": 0.3, "scdet_thr": 10,
    "hook_size": 88, "punch_size": 64, "text_bg": False,
}

FONT    = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────
#  UTILS
# ─────────────────────────────────────────────────────────────────────
def run(cmd, silent=False):
    if not silent: print(f"  ▸ {cmd[:110]}")
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
            if score > 0 and pts > 0.2:
                changes.append((pts, score))
    except: pass
    return sorted(changes)

def get_audio_rms(path):
    r = run(f'ffprobe -v quiet -f lavfi -i "amovie={path},astats=metadata=1:reset=1" '
            f'-show_entries frame_tags=lavfi.astats.Overall.RMS_level -of csv=p=0', silent=True)
    vals = [float(l) for l in r.stdout.strip().split('\n') if l.strip() and float(l) > -100]
    return sum(vals)/len(vals) if vals else -60.0

def get_motion_score(path, duration):
    r = run(f'ffprobe -v quiet -f lavfi '
            f'-i "movie={path},fps=4,split[a][b];[a][b]psnr" '
            f'-show_entries frame_tags=lavfi.psnr.mse_avg -of csv=p=0 -t {min(duration,4.0)}', silent=True)
    vals = [float(l) for l in r.stdout.strip().split('\n') if l.strip() and 0 < float(l) < 9999]
    return sum(vals)/len(vals) if vals else 0.0

# ─────────────────────────────────────────────────────────────────────
#  ANALYSE CLIP
# ─────────────────────────────────────────────────────────────────────
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

def score_roles(clips_data):
    n = len(clips_data)
    if n == 1: return [("hook_core_punch", clips_data[0])]
    if n == 2:
        s0 = clips_data[0]["early"]*12 + clips_data[0]["peak"]
        s1 = clips_data[1]["early"]*12 + clips_data[1]["peak"]
        return [("hook", clips_data[0 if s0>=s1 else 1]),
                ("punch", clips_data[1 if s0>=s1 else 0])]
    def hs(c): return c["early"]*12 + c["peak"]*2 + c["motion"]*0.5 - c["duration"]*0.5
    def ps(c): return c["late"]*12 + (c["rms"]+60)*0.8 + c["peak"] - c["density"]*2
    hook_c  = max(clips_data, key=hs)
    rem     = [c for c in clips_data if c["idx"] != hook_c["idx"]]
    punch_c = max(rem, key=ps)
    cores   = [c for c in rem if c["idx"] != punch_c["idx"]]
    result  = [("hook", hook_c)] + [("core", c) for c in cores] + [("punch", punch_c)]
    for role, c in result:
        print(f"  r{c['idx']} → {role.upper():8} motion={c['motion']:.1f} rms={c['rms']:.0f}dB")
    return result

# ─────────────────────────────────────────────────────────────────────
#  IA — VISION + TEXTES
# ─────────────────────────────────────────────────────────────────────
def extract_frames_b64(path, n=3):
    dur = get_duration(path)
    frames = []
    for i, t in enumerate([dur*0.08, dur*0.45, dur*0.82][:n]):
        out = f"{path}_f{i}.jpg"
        run(f'ffmpeg -y -ss {t:.3f} -i "{path}" -vframes 1 -q:v 2 "{out}"', silent=True)
        if os.path.exists(out):
            with open(out, "rb") as f:
                frames.append(base64.b64encode(f.read()).decode())
    return frames

def call_claude(messages, max_tokens=600, system=None):
    payload = {"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens, "messages": messages}
    if system: payload["system"] = system
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode(),
                headers={"Content-Type":"application/json",
                         "x-api-key": API_KEY,
                         "anthropic-version":"2023-06-01"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
            text = data["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
            return text
        except Exception as e:
            print(f"  ⚠ API attempt {attempt+1}: {e}")
            if attempt == 0: time.sleep(2)
    return None

def ai_analyze_and_generate(clips_data, roles_order, custom_hook="", custom_punch=""):
    """Un seul appel IA : analyse visuelle + génération textes + noms de cartes."""
    print("\n  [IA] Analyse + génération textes...")
    content = []

    SYSTEM = (
        "Tu es le copywriter de la chaine TikTok LES CRADOS — cartes a collectionner "
        "humoristiques style Garbage Pail Kids version francaise. "
        "Ton humour : absurde pince-sans-rire, noir leger, culture internet. "
        "Tu lis les noms sur les cartes et tu t en inspires DIRECTEMENT. "
        "REGLES ABSOLUES pour les textes : zero apostrophe, zero deux-points, "
        "zero virgule, zero guillemets. Sinon FFmpeg plante."
    )

    for role, clip in roles_order:
        frames = extract_frames_b64(clip["path"])
        if not frames: continue
        content.append({"type":"text","text":f"\n--- Clip {role.upper()} ---"})
        for j, b64 in enumerate(frames):
            content.append({"type":"text","text":f"Frame {['debut','milieu','fin'][j]}:"})
            content.append({"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}})

    constraints = []
    if custom_hook:  constraints.append(f"HOOK impose : \"{custom_hook}\"")
    if custom_punch: constraints.append(f"PUNCHLINE imposee : \"{custom_punch}\"")
    c_txt = "\n".join(constraints) if constraints else "Aucune contrainte."

    content.append({"type":"text","text":(
        f"\nContraintes : {c_txt}\n\n"
        "ETAPE 1 — Lis les noms sur les cartes (ex: JEROME GASTRONOME, SADIQUE ERIC, etc)\n"
        "ETAPE 2 — Genere 3 textes qui UTILISENT ces noms ou s en inspirent directement.\n\n"
        "1. HOOK (2 a 4 mots, TOUT EN MAJUSCULES) :\n"
        "   → Choc immédiat. Exemples avec noms : 'JEROME FAIT QUOI', 'NON MAIS JEROME', "
        "'SADIQUE ERIC ENCORE', 'ATTENDS JEROME'\n"
        "   → OU sans nom : 'ATTENDS QUOI', 'NON MAIS LA', 'CA EXISTE VRAIMENT'\n\n"
        "2. CORE_TEXT (3 a 5 mots, peut etre vide '') :\n"
        "   → Commentaire pince-sans-rire sur l action. Peut integrer le nom.\n"
        "   → Ex: 'Jerome approuve', 'Crado certifie', 'Situation normale'\n\n"
        "3. PUNCHLINE (5 a 8 mots + 1 emoji possible) :\n"
        "   → Chute absurde. Peut utiliser le nom. Ex: 'Jerome fait ca depuis des annees 💀'\n"
        "   → Ou sans nom : 'Note de vie 0 sur 10 🗑'\n\n"
        "Hook → Core → Punchline forment une micro-histoire drole.\n\n"
        "Reponds UNIQUEMENT JSON strict sans markdown :\n"
        "{\"card_names\":[\"nom1\",\"nom2\"],\"hook\":\"TEXTE\",\"core_text\":\"Texte\",\"punchline\":\"Texte\"}"
    )})

    result = call_claude([{"role":"user","content":content}], max_tokens=400, system=SYSTEM)
    if not result: return None

    try:
        data = json.loads(result)
        clean = lambda s: (s.replace("'","").replace(":"," ").replace('"',' ')
                            .replace(",","").replace("  "," ")
                            # supprimer emojis (Liberation ne les supporte pas)
                            .encode('ascii','ignore').decode('ascii').strip())
        hook      = clean(custom_hook  if custom_hook  else data.get("hook",""))
        core      = clean(data.get("core_text",""))
        punchline = clean(custom_punch if custom_punch else data.get("punchline",""))
        names     = data.get("card_names", [])
        print(f"  ✓ Cartes lues : {names}")
        print(f"  ✓ Hook        : {hook}")
        print(f"  ✓ Core        : {core}")
        print(f"  ✓ Punchline   : {punchline}")
        return hook, core, punchline, names
    except Exception as e:
        print(f"  ⚠ Parse echoue ({e}) — raw: {result[:100]}")
        return None

def smart_fallback(custom_hook="", custom_punch="", seed=""):
    """Pool de textes percutants style Les Crados — utilisé sans API."""
    HOOKS = [
        "ATTENDS QUOI","NON MAIS LA","CA EXISTE VRAIMENT","T AS VU CA",
        "MAIS QUI A FAIT CA","REGARDE MOI CA","TROP CRADE","IL EST FOU CE GARS",
        "SCANDALE TOTAL","GAME OVER","WTF ABSOLU","INTERDIT AUX FRAGILES",
        "NIVEAU ULTIME","ON EST D ACCORD",
    ]
    PUNCHES = [
        "Les Crados frappent encore",
        "Y a vraiment pas de mots",
        "Ma mere elle sait pas que je regarde ca",
        "Note de vie 0 sur 10",
        "Certifie degoutant",
        "La honte du quartier",
        "Science sans conscience etc",
        "Quelqu un a valide ca srsly",
        "Chef-d oeuvre ou crime je sais pas",
        "Pas vu ca depuis le bahut",
        "Talent gache au service du chaos",
        "Magistral dans le genre horrible",
        "On lui a rien demande mais bon",
        "Interdit aux moins de 30 ans",
    ]
    CORES = ["La carte qui tue","Crado certifie","Niveau max atteint",
             "Situation normale","Comme d hab","","",""]

    rng = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8],16))
    h = custom_hook.replace("'","").replace(":"," ") if custom_hook else rng.choice(HOOKS)
    p = custom_punch.replace("'","").replace(":"," ") if custom_punch else rng.choice(PUNCHES)
    c = rng.choice(CORES)
    return h, c, p

# ─────────────────────────────────────────────────────────────────────
#  TEXTES ANIMÉS — STYLE TIKTOK VIRAL
# ─────────────────────────────────────────────────────────────────────
def dynamic_fontsize(text, base_sz, max_w, char_ratio=0.58):
    """Réduit la police si le texte dépasse max_w pixels."""
    estimated = len(text) * base_sz * char_ratio
    if estimated > max_w:
        return max(36, int(base_sz * max_w / estimated))
    return base_sz

def write_text_filter(hook, core_text, punchline, total_dur):
    """
    Animations TikTok virales :
    - HOOK     : POP depuis 0 + bounce + ROUGE #FF2D55 + shadow forte
    - CORE     : slide depuis droite + blanc + ombre
    - PUNCHLINE: bounce depuis bas + shake final + JAUNE FLUO #FFE600
    """
    W, H  = [int(x) for x in CFG["resolution"].split("x")]
    # Tailles adaptées à la longueur du texte (max 92% de la largeur)
    max_w = int(W * 0.92)
    h_sz  = dynamic_fontsize(hook,      CFG["hook_size"],  max_w)
    p_sz  = dynamic_fontsize(punchline, CFG["punch_size"], max_w)
    c_sz  = dynamic_fontsize(core_text, max(48, CFG["punch_size"]-10), max_w) if core_text else 48

    def ft(t): return f"{t:.3f}"

    # zones safe (au-dessus du nom de carte en bas)
    hook_y  = 115
    pl_y    = H - 145 - p_sz
    core_y  = H // 2 - c_sz // 2

    # timings
    h_pop   = 0.15
    h_hold  = 2.0
    h_out   = 2.5

    ci      = 2.6
    cs      = 2.85
    ch      = min(4.8, total_dur - 2.6)
    co      = min(5.1, total_dur - 2.3)

    pi      = max(0.0, total_dur - 2.8)
    pb      = pi + 0.20
    psh     = max(pb, total_dur - 0.55)
    po      = total_dur

    # ── HOOK : pop bounce depuis le haut ──────────────────────────
    h_y = (
        f"if(lt(t\\,{ft(h_pop)})\\,"
        # pop depuis hook_y-50 vers hook_y
        f"{hook_y-50}+(t/{ft(max(h_pop,0.01))})*50\\,"
        f"{hook_y})"
    )
    h_alpha = (
        f"if(lt(t\\,{ft(h_pop)})\\,t/{ft(max(h_pop,0.01))}\\,"
        f"if(lt(t\\,{ft(h_hold)})\\,1\\,"
        f"max(0\\,({ft(h_out)}-t)/{ft(max(h_out-h_hold,0.01))}))"
        f")"
    )
    hook_f = (
        f"drawtext=text='{hook}':"
        f"fontfile={FONT}:fontsize={h_sz}:"
        f"fontcolor=#FF2D55:borderw=10:bordercolor=black@0.9:"
        f"shadowx=5:shadowy=5:shadowcolor=black@0.8:"
        f"x=(w-text_w)/2:y={h_y}:"
        f"alpha='{h_alpha}':"
        f"enable='between(t\\,0\\,{ft(h_out)})'"
    )

    # ── CORE : slide depuis la droite ─────────────────────────────
    core_f = ""
    if core_text:
        c_alpha = (
            f"if(lt(t\\,{ft(cs)})\\,(t-{ft(ci)})/{ft(max(cs-ci,0.01))}\\,"
            f"if(lt(t\\,{ft(ch)})\\,0.95\\,"
            f"max(0\\,({ft(co)}-t)/{ft(max(co-ch,0.01))}))"
            f")"
        )
        # slide x de droite vers centre
        c_x = (
            f"if(lt(t\\,{ft(cs)})\\,"
            f"w-(t-{ft(ci)})*w/{ft(max(cs-ci,0.01))}+(w-text_w)/2\\,"
            f"(w-text_w)/2)"
        )
        core_f = (
            f",drawtext=text='{core_text}':"
            f"fontfile={FONT}:fontsize={c_sz}:"
            f"fontcolor=white:borderw=7:bordercolor=black:"
            f"shadowx=4:shadowy=4:shadowcolor=black@0.9:"
            f"x={c_x}:y={core_y}:"
            f"alpha='{c_alpha}':"
            f"enable='between(t\\,{ft(ci)}\\,{ft(co)})'"
        )

    # ── PUNCHLINE : bounce + shake ────────────────────────────────
    pl_y_expr = (
        f"if(lt(t\\,{ft(pb)})\\,"
        # arrive depuis pl_y+90, overshoot puis settle
        f"{pl_y+90}-(t-{ft(pi)})*110/{ft(max(pb-pi,0.01))}\\,"
        f"if(lt(t\\,{ft(pb+0.1)})\\,"
        f"{pl_y-20}+(t-{ft(pb)})*20/{ft(0.1)}\\,"
        f"{pl_y}))"
    )
    pl_x = (
        f"if(lt(t\\,{ft(psh)})\\,(w-text_w)/2\\,"
        # shake ±10px à 70Hz
        f"(w-text_w)/2+10*sin((t-{ft(psh)})*70))"
    )
    pl_alpha = (
        f"if(lt(t\\,{ft(pb)})\\,(t-{ft(pi)})/{ft(max(pb-pi,0.01))}\\,"
        f"if(lt(t\\,{ft(po-0.2)})\\,1\\,"
        f"max(0\\,({ft(po)}-t)/0.2))"
        f")"
    )
    pl_f = (
        f",drawtext=text='{punchline}':"
        f"fontfile={FONT}:fontsize={p_sz}:"
        f"fontcolor=#FFE600:borderw=9:bordercolor=black:"
        f"shadowx=5:shadowy=5:shadowcolor=black@0.9:"
        f"x={pl_x}:y={pl_y_expr}:"
        f"alpha='{pl_alpha}':"
        f"enable='between(t\\,{ft(pi)}\\,{ft(po)})'"
    )

    # fond optionnel
    bg = ""
    if CFG.get("text_bg"):
        pad = 14
        bg = (
            f"drawbox=x=0:y={hook_y-pad}:w=iw:h={h_sz+pad*2}:color=black@0.55:t=fill:"
            f"enable='between(t\\,0\\,{ft(h_out)})',"
            f"drawbox=x=0:y={pl_y-pad}:w=iw:h={p_sz+pad*2}:color=black@0.55:t=fill:"
            f"enable='between(t\\,{ft(pi)}\\,{ft(po)})',"
        )
        if core_text:
            bg += (f"drawbox=x=0:y={core_y-pad}:w=iw:h={c_sz+pad*2}:color=black@0.55:t=fill:"
                   f"enable='between(t\\,{ft(ci)}\\,{ft(co)})',")

    full = bg + hook_f + core_f + pl_f
    with open("text_filter.txt", "w", encoding="utf-8") as f:
        f.write(full)

def apply_text_overlay(src, out, hook, core_text, punchline):
    dur = get_duration(src)
    write_text_filter(hook, core_text, punchline, dur)
    r = run(f'ffmpeg -y -i "{src}" -filter_script:v text_filter.txt '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print("  ⚠ drawtext echoue — copie sans texte")
        run(f'cp "{src}" "{out}"', silent=True)

# ─────────────────────────────────────────────────────────────────────
#  EFFETS VIDÉO
# ─────────────────────────────────────────────────────────────────────
def make_vf(src_w, src_h):
    W, H = [int(x) for x in CFG["resolution"].split("x")]
    fps  = CFG["fps"]
    if src_w/src_h <= W/H + 0.05:
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}"
    sh = int(src_h * W / src_w); sh -= sh % 2
    return f"scale={W}:{sh},pad={W}:{H}:0:{(H-sh)//2}:black,setsar=1,fps={fps}"

def make_flash(color="white", name="flash.mp4"):
    """
    Flash coloré selon le segment suivant :
    → hook : blanc pur (choc maximal)
    → core : orange chaud (transition douce)
    → punch: rouge sombre (annonce la chute)
    """
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
    print(f"  ≈ Coupe forcee {safe:.3f}s")
    return safe

def grade_filter(role, duration):
    """
    Colour grading par rôle — optimisé rétention watch time.

    HOOK   : hyper-saturé, surexposé, contraste brutal, vignette pulsante
             → urgence visuelle, force l'attention dans les 1ères secondes
    CORE   : légèrement chaud (+teinte orange), naturel, vignette douce
             → confort visuel, le viewer s'installe et regarde
    PUNCH  : désaturé froid, vignette forte, légèrement sombre
             → effet cinéma, signale la chute, mémorable

    eq(brightness, contrast, saturation, gamma) :
      brightness : -1.0 (noir) → 1.0 (blanc)  | neutre = 0.0
      contrast   : -1000 → 1000               | neutre = 1.0
      saturation : 0.0 (NB) → 3.0 (ultra)    | neutre = 1.0
    """
    if role == 'hook':
        eq   = "eq=brightness=0.06:contrast=1.25:saturation=1.65:gamma=0.92"
        vign = "vignette=PI/5"   # vignette(angle) — syntaxe courte compatible
        return f"{eq},{vign}"

    elif role == 'core':
        # Léger boost gamma_r pour teinte chaude orangée
        eq   = "eq=brightness=0.02:contrast=1.08:saturation=1.15:gamma_r=0.94"
        vign = "vignette=PI/6"
        return f"{eq},{vign}"

    else:  # punch
        # Froid désaturé + sombre + vignette lourde + boost gamma_b (teinte froide)
        eq   = "eq=brightness=-0.04:contrast=1.18:saturation=0.72:gamma=1.05:gamma_b=0.90"
        vign = "vignette=PI/3"
        return f"{eq},{vign}"

def trim_segment(src, out, duration, vf, role='core'):
    # Colour grading injecté après le recadrage
    cg = grade_filter(role, duration)
    full_vf = f"{vf},{cg}"
    r = run(f'ffmpeg -y -i "{src}" -t {duration:.4f} -vf "{full_vf}" '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    # Fallback sans grading si erreur
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print(f"  ⚠ Grading echoue sur {role} — fallback sans grade")
        run(f'ffmpeg -y -i "{src}" -t {duration:.4f} -vf "{vf}" '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')

def apply_zoom_punch(src, out, punch_t):
    fps = CFG["fps"]; scale = CFG["zoom_scale"]
    pf  = int(punch_t * fps); zi, zo = 3, 8
    W, H = [int(x) for x in CFG["resolution"].split("x")]
    ze = (f"if(between(on,{pf},{pf+zi}),1.0+(on-{pf})*{scale-1:.3f}/{zi},"
          f"if(between(on,{pf+zi},{pf+zi+zo}),{scale:.3f}-({scale-1:.3f})*(on-{pf+zi})/{zo},1.0))")
    vf = f"zoompan=z='{ze}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
    r  = run(f'ffmpeg -y -i "{src}" -vf "{vf}" '
             f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        run(f'cp "{src}" "{out}"', silent=True)

def concat_segments(segments, out):
    with open("list.txt","w") as f:
        [f.write(f"file '{s}'\n") for s in segments]
    run(f'ffmpeg -y -f concat -safe 0 -i list.txt '
        f'-c:v libx264 -crf {CFG["crf"]} -preset fast '
        f'-pix_fmt yuv420p -movflags +faststart -an "{out}"')

def merge_audio(video, audio_src, out):
    vd = get_duration(video); fd = CFG["fade_dur"]
    run(f'ffmpeg -y -i "{video}" -i "{audio_src}" '
        f'-map 0:v -map 1:a -t {vd:.4f} '
        f'-c:v copy -c:a aac -b:a {CFG["audio_br"]}k '
        f'-af "afade=t=out:st={max(0,vd-fd-0.1):.3f}:d={fd}" '
        f'-movflags +faststart "{out}"')

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
    print(f"▶ ViraCut Les Crados v4 — {CFG['resolution']} {CFG['fps']}fps")

    videos = data.get('videos', [])
    print(f"\n[1/7] Extraction de {len(videos)} clip(s)")

    # 1. Extraction + analyse
    clips_data = []
    for i, v in enumerate(videos):
        path = f"r{i}.mp4"
        with open(path,"wb") as fout:
            fout.write(base64.b64decode(v['data']))
        print(f"\n  Clip r{i}...")
        cd = analyze_clip(path, i)
        print(f"  → {cd['duration']:.2f}s  {cd['width']}x{cd['height']}  "
              f"changes={len(cd['changes'])}  motion={cd['motion']:.1f}  rms={cd['rms']:.0f}dB")
        clips_data.append(cd)

    # 2. Ordre narratif
    print(f"\n[2/7] Classification narrative")
    video_roles  = data.get('videos', [])
    manual_roles = {v.get('role','auto') for v in video_roles}

    if CFG["auto_order"] and manual_roles == {'auto'}:
        roles_order = score_roles(clips_data)
    else:
        role_map    = {'hook':'hook','core':'core','punch':'punch','auto':None}
        roles_order = []
        for i,v in enumerate(video_roles):
            r = role_map.get(v.get('role','auto')) or ['hook','core','punch'][min(i,2)]
            roles_order.append((r, clips_data[i]))
        print("  → Ordre manuel")

    durations = []
    for role,_ in roles_order:
        if 'hook_core_punch' in role: durations.append(CFG["hook_dur"]+CFG["core_dur"]+CFG["punch_dur"])
        elif role=='hook':  durations.append(CFG["hook_dur"])
        elif role=='core':  durations.append(CFG["core_dur"])
        else:               durations.append(CFG["punch_dur"])

    # 3+4. IA : analyse vision + textes (un seul appel)
    print(f"\n[3/7] Analyse IA")
    hook_text = core_text = punch_text = ""

    if CFG["ai_text"] and API_KEY:
        result = ai_analyze_and_generate(
            clips_data, roles_order,
            CFG.get("custom_hook",""), CFG.get("custom_punch",""))
        if result:
            hook_text, core_text, punch_text, _ = result

    if not hook_text:
        if not API_KEY: print("  ⚠ Pas d API key — fallback Les Crados")
        seed = "".join(cd["path"] for cd in clips_data)
        hook_text, core_text, punch_text = smart_fallback(
            CFG.get("custom_hook",""), CFG.get("custom_punch",""), seed=seed)
        print(f"  → Hook      : {hook_text}")
        if core_text: print(f"  → Core      : {core_text}")
        print(f"  → Punchline : {punch_text}")

    # 5. Découpe + effets
    print(f"\n[5/7] Decoupe + effets")

    # Flash colorés selon le rôle du segment SUIVANT
    FLASH_COLORS = {'hook': 'white', 'core': 'orange', 'punch': '0x8B0000'}
    if CFG["flash_cut"]:
        for role_name, color in FLASH_COLORS.items():
            make_flash(color=color, name=f"flash_{role_name}.mp4")

    segments = []
    for i, ((role, clip), target) in enumerate(zip(roles_order, durations)):
        path    = clip["path"]; changes = clip["changes"]
        dur     = clip["duration"]; w,h = clip["width"], clip["height"]
        cut_t   = best_cut(changes, target, dur)
        raw_seg = f"raw_seg{i}.mp4"
        trim_segment(path, raw_seg, cut_t, make_vf(w, h), role=role)
        seg_out = f"seg{i}.mp4"
        if CFG["zoom_punch"] and role in ('core','hook_core_punch'):
            in_seg = [(t,s) for t,s in changes if 0.3 < t < cut_t]
            if in_seg:
                mid = cut_t/2
                pt  = max(in_seg, key=lambda x: x[1]*(1-abs(x[0]-mid)/max(mid,0.1)))
                print(f"  → Zoom punch r{clip['idx']} à {pt[0]:.3f}s")
                apply_zoom_punch(raw_seg, seg_out, pt[0])
            else: run(f'cp "{raw_seg}" "{seg_out}"', silent=True)
        else: run(f'cp "{raw_seg}" "{seg_out}"', silent=True)
        segments.append(seg_out)
        print(f"  ✓ seg{i} ({role}) → {get_duration(seg_out):.3f}s")

    # 6. Assemblage
    print(f"\n[6/7] Assemblage")
    interleaved = []
    for i, seg in enumerate(segments):
        interleaved.append(seg)
        if i < len(segments) - 1 and CFG["flash_cut"]:
            # Flash = couleur du segment SUIVANT
            next_role = roles_order[i + 1][0]
            flash_file = f"flash_{next_role}.mp4"
            if os.path.exists(flash_file):
                interleaved.append(flash_file)
    concat_segments(interleaved, "no_text.mp4")

    # 7. Textes + Audio
    print(f"\n[7/7] Textes + Audio")
    print(f"  Hook={hook_text!r}  Core={core_text!r}  Punch={punch_text!r}")
    apply_text_overlay("no_text.mp4", "no_audio.mp4", hook_text, core_text, punch_text)

    audio_clip = None
    for cd in clips_data:
        if run(f'ffprobe -v quiet -select_streams a -show_streams "{cd["path"]}"', silent=True).stdout.strip():
            audio_clip = cd["path"]; break

    if audio_clip: merge_audio("no_audio.mp4", audio_clip, "output.mp4")
    else: os.rename("no_audio.mp4", "output.mp4")

    if os.path.exists("output.mp4"):
        fd = get_duration("output.mp4"); fw,fh = get_dimensions("output.mp4")
        print(f"\n{'='*52}")
        print(f"✅ SUCCES  {fw}x{fh}  {fd:.2f}s")
        print(f"   Hook       : {hook_text}")
        if core_text: print(f"   Core       : {core_text}")
        print(f"   Punchline  : {punch_text}")
        print(f"{'='*52}")
    else:
        print("\n❌ ECHEC : output.mp4 non genere")

if __name__ == "__main__":
    start()
