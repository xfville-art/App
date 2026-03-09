"""
render.py — ViraCut v3
Pipeline intelligent : analyse IA multi-frames → narrative → effets adaptés
"""
import json, base64, os, subprocess, urllib.request, urllib.error, time

# ─────────────────────────────────────────────────────────────────────
#  CONFIG (overridable depuis p.json options)
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "hook_dur":    2.0,
    "core_dur":    2.5,
    "punch_dur":   3.0,
    "tolerance":   0.7,
    "flash_cut":   True,
    "zoom_punch":  True,
    "zoom_scale":  1.08,
    "ai_text":     True,
    "auto_order":  True,
    "custom_hook":  "",
    "custom_punch": "",
    "resolution":  "720x1280",
    "fps":         24,
    "crf":         18,
    "audio_br":    192,
    "fade_dur":    0.3,
    "scdet_thr":   10,
    "hook_size":   86,
    "punch_size":  62,
    "text_bg":     False,
}

FONT    = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────
#  UTILS FFMPEG
# ─────────────────────────────────────────────────────────────────────
def run(cmd, silent=False):
    if not silent:
        print(f"  ▸ {cmd[:100]}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and not silent:
        print(f"    ✗ {r.stderr[-200:]}")
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

def get_scene_changes(path, threshold=None):
    thr = threshold or CFG["scdet_thr"]
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
    return sorted(changes, key=lambda x: x[0])

def get_audio_rms(path):
    """Mesure le niveau audio moyen — proxy pour intensité/énergie du clip."""
    r = run(f'ffprobe -v quiet -f lavfi -i "amovie={path},astats=metadata=1:reset=1" '
            f'-show_entries frame_tags=lavfi.astats.Overall.RMS_level '
            f'-of csv=p=0', silent=True)
    vals = []
    for line in r.stdout.strip().split('\n'):
        try:
            v = float(line)
            if v > -100:
                vals.append(v)
        except: pass
    return sum(vals) / len(vals) if vals else -60.0

def get_motion_score(path, duration):
    """Score de mouvement via différence de frames (PSNR inversé)."""
    r = run(f'ffprobe -v quiet -f lavfi '
            f'-i "movie={path},fps=4,split[a][b];[a][b]psnr" '
            f'-show_entries frame_tags=lavfi.psnr.mse_avg '
            f'-of csv=p=0 -t {min(duration, 4.0)}', silent=True)
    vals = []
    for line in r.stdout.strip().split('\n'):
        try:
            v = float(line)
            if 0 < v < 9999:
                vals.append(v)
        except: pass
    return sum(vals) / len(vals) if vals else 0.0

# ─────────────────────────────────────────────────────────────────────
#  ANALYSE DE CLIP
# ─────────────────────────────────────────────────────────────────────
def analyze_clip(path, idx):
    """Collecte toutes les métriques d'un clip."""
    dur       = get_duration(path)
    w, h      = get_dimensions(path)
    changes   = get_scene_changes(path)
    rms       = get_audio_rms(path)
    motion    = get_motion_score(path, dur)

    # Score d'énergie composite
    scene_density  = len(changes) / max(dur, 0.1)
    early_changes  = sum(1 for t, s in changes if t <= 2.0)
    late_changes   = sum(1 for t, s in changes if t >= dur * 0.6)
    peak_score     = max((s for t, s in changes), default=0)

    return {
        "path":           path,
        "idx":            idx,
        "duration":       dur,
        "width":          w,
        "height":         h,
        "changes":        changes,
        "rms":            rms,
        "motion":         motion,
        "scene_density":  scene_density,
        "early_changes":  early_changes,
        "late_changes":   late_changes,
        "peak_score":     peak_score,
    }

def score_roles(clips_data):
    """
    Attribue les rôles hook/core/punchline selon un scoring multidimensionnel.
    Hook     = beaucoup d'activité tôt + fort impact visuel (peak_score élevé)
    Core     = densité scène moyenne + mouvement soutenu
    Punchline = fin forte + audio fort + activité tardive
    """
    n = len(clips_data)
    if n == 1:
        return [("hook_core_punch", clips_data[0])]
    if n == 2:
        # Le plus dynamique en premier
        s0 = clips_data[0]["early_changes"] * 10 + clips_data[0]["peak_score"]
        s1 = clips_data[1]["early_changes"] * 10 + clips_data[1]["peak_score"]
        if s0 >= s1:
            return [("hook", clips_data[0]), ("punch", clips_data[1])]
        else:
            return [("hook", clips_data[1]), ("punch", clips_data[0])]

    # 3+ clips : scoring 3D
    def hook_score(c):
        return (c["early_changes"] * 12
                + c["peak_score"] * 2
                + c["motion"] * 0.5
                - c["duration"] * 0.5)

    def punch_score(c):
        return (c["late_changes"] * 12
                + (c["rms"] + 60) * 0.8   # audio plus fort = punchline
                + c["peak_score"]
                - c["scene_density"] * 2)

    def core_score(c):
        return (c["scene_density"] * 8
                + c["motion"] * 0.8
                + c["duration"] * 0.5)

    hooks   = sorted(clips_data, key=hook_score, reverse=True)
    hook_c  = hooks[0]
    rem     = [c for c in clips_data if c["idx"] != hook_c["idx"]]
    punch_c = max(rem, key=punch_score)
    cores   = [c for c in rem if c["idx"] != punch_c["idx"]]
    # S'il y a plusieurs cores, prendre celui avec le meilleur score core
    if len(cores) > 1:
        cores = sorted(cores, key=core_score, reverse=True)

    result = [("hook", hook_c)] + [("core", c) for c in cores] + [("punch", punch_c)]

    for role, c in result:
        print(f"  ✓ r{c['idx']} → {role.upper():8s} "
              f"(motion={c['motion']:.1f} rms={c['rms']:.0f}dB "
              f"early={c['early_changes']} late={c['late_changes']})")
    return result

# ─────────────────────────────────────────────────────────────────────
#  IA — ANALYSE VISION MULTI-FRAMES
# ─────────────────────────────────────────────────────────────────────
def extract_frames_b64(path, n_frames=3):
    """Extrait n frames réparties sur le clip (début, milieu, fin)."""
    dur    = get_duration(path)
    frames = []
    times  = [dur * 0.1, dur * 0.5, dur * 0.85][:n_frames]
    for i, t in enumerate(times):
        out = f"{path}_f{i}.jpg"
        run(f'ffmpeg -y -ss {t:.3f} -i "{path}" -vframes 1 -q:v 2 "{out}"', silent=True)
        if os.path.exists(out):
            with open(out, "rb") as f:
                frames.append(base64.b64encode(f.read()).decode())
    return frames

def call_claude(messages, max_tokens=600, system=None):
    """Appel API Anthropic avec retry."""
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        payload["system"] = system

    for attempt in range(2):
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": API_KEY,
                    "anthropic-version": "2023-06-01"
                }
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return text
        except Exception as e:
            print(f"  ⚠ Tentative {attempt+1} échouée : {e}")
            if attempt == 0: time.sleep(2)
    return None

def ai_analyze_clips(clips_data, roles_order):
    """
    Étape 1 : Claude analyse visuellement chaque clip.
    Retourne une description narrative par clip.
    """
    if not API_KEY:
        return None

    print("\n  [IA] Analyse visuelle des clips...")
    content = []

    system = (
        "Tu es un expert en montage TikTok viral spécialisé dans les contenus "
        "humoristiques style Garbage Pail Kids / cartes animées absurdes. "
        "Tu analyses des clips vidéo pour comprendre leur contenu visuel et émotionnel."
    )

    for role, clip in roles_order:
        frames = extract_frames_b64(clip["path"], n_frames=3)
        if not frames:
            continue
        content.append({
            "type": "text",
            "text": f"\n--- Clip '{role.upper()}' (r{clip['idx']}) ---"
        })
        for j, b64 in enumerate(frames):
            label = ["début", "milieu", "fin"][j]
            content.append({"type": "text", "text": f"Frame {label} :"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
            })

    content.append({
        "type": "text",
        "text": (
            "\nPour chaque clip, décris en 1-2 phrases :\n"
            "- Ce qu'on voit visuellement (personnage, action, ambiance)\n"
            "- Le registre émotionnel (WTF, drôle, choc, absurde, cool)\n"
            "- Un mot-clé thématique\n\n"
            "Réponds UNIQUEMENT en JSON strict :\n"
            '{"clips": [{"role":"hook","description":"...","emotion":"...","theme":"..."}, ...]}'
        )
    })

    result = call_claude([{"role": "user", "content": content}], max_tokens=500, system=system)
    if not result:
        return None

    try:
        data = json.loads(result)
        return data.get("clips", [])
    except:
        print(f"  ⚠ Parse analyse échoué")
        return None


def ai_generate_texts(clips_analysis, roles_order, custom_hook="", custom_punch=""):
    """
    Étape 2 : génère les textes sur la base de l'analyse visuelle.
    Produit hook + texte core (optionnel) + punchline cohérents narrativement.
    """
    if not API_KEY:
        return _default_texts(custom_hook, custom_punch)

    print("\n  [IA] Génération des textes narratifs...")

    # Construire le contexte narratif depuis l'analyse
    context_parts = []
    for role, clip in roles_order:
        desc = ""
        if clips_analysis:
            for c in clips_analysis:
                if c.get("role") == role:
                    desc = f" — {c.get('description','')} (émotion: {c.get('emotion','')})"
                    break
        context_parts.append(f"• {role.upper()}{desc}")

    context = "\n".join(context_parts)

    constraints = []
    if custom_hook:
        constraints.append(f"HOOK imposé (utilise tel quel) : \"{custom_hook}\"")
    if custom_punch:
        constraints.append(f"PUNCHLINE imposée : \"{custom_punch}\"")

    constraint_txt = "\n".join(constraints) if constraints else "Aucune contrainte imposée."

    prompt = (
        f"Contenu des clips dans l'ordre du montage :\n{context}\n\n"
        f"Contraintes : {constraint_txt}\n\n"
        "Génère 3 textes pour cette vidéo TikTok :\n\n"
        "1. HOOK (affiché 0→2.5s, en haut) :\n"
        "   - Max 4 mots, MAJUSCULES\n"
        "   - Choc / WTF / question intrigante\n"
        "   - Doit donner envie de continuer à regarder\n"
        "   - Pas d'apostrophe, pas de deux-points\n\n"
        "2. CORE_TEXT (affiché au milieu, 2.5s→5s, au centre) :\n"
        "   - Max 5 mots, style caption TikTok\n"
        "   - Commente l'action en cours avec humour décalé\n"
        "   - Pas d'apostrophe, pas de deux-points\n\n"
        "3. PUNCHLINE (affiché fin, en bas) :\n"
        "   - Max 6 mots, humour absurde/décalé\n"
        "   - Doit créer une chute narrative par rapport au hook\n"
        "   - Peut finir par UN emoji simple\n"
        "   - Pas d'apostrophe, pas de deux-points\n\n"
        "IMPORTANT : les 3 textes doivent former une micro-narration cohérente.\n"
        "Hook pose une question/tension → Core commente → Punchline résout de façon absurde.\n\n"
        "Réponds UNIQUEMENT en JSON strict :\n"
        '{"hook":"TEXTE","core_text":"Texte","punchline":"Texte emoji"}'
    )

    result = call_claude(
        [{"role": "user", "content": prompt}],
        max_tokens=300,
        system=(
            "Tu es un copywriter expert TikTok viral pour une chaîne humoristique "
            "de cartes animées style Garbage Pail Kids française. "
            "Ton style : absurde, décalé, culture internet, humour noir léger. "
            "Jamais banal, jamais générique."
        )
    )

    if not result:
        return _default_texts(custom_hook, custom_punch)

    try:
        data = json.loads(result)
        clean = lambda s: s.replace("'", " ").replace(":", " ").replace('"', ' ').strip()
        hook       = clean(custom_hook  if custom_hook  else data.get("hook", "TAS VU CA"))
        core_text  = clean(data.get("core_text", ""))
        punchline  = clean(custom_punch if custom_punch else data.get("punchline", "Impossible de pas rire"))
        print(f"  ✓ Hook       : {hook}")
        print(f"  ✓ Core text  : {core_text}")
        print(f"  ✓ Punchline  : {punchline}")
        return hook, core_text, punchline
    except Exception as e:
        print(f"  ⚠ Parse textes échoué ({e})")
        return _default_texts(custom_hook, custom_punch)


def _default_texts(custom_hook="", custom_punch=""):
    hook = custom_hook.replace("'", " ").replace(":", " ") if custom_hook else "TAS VU CA"
    pl   = custom_punch.replace("'", " ").replace(":", " ") if custom_punch else "Impossible de pas rire"
    return hook, "", pl

# ─────────────────────────────────────────────────────────────────────
#  FILTRES VIDÉO
# ─────────────────────────────────────────────────────────────────────
def make_vf(src_w, src_h):
    W, H = [int(x) for x in CFG["resolution"].split("x")]
    fps  = CFG["fps"]
    src_ratio = src_w / src_h
    if src_ratio <= W / H + 0.05:
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1,fps={fps}")
    else:
        scaled_h = int(src_h * W / src_w)
        if scaled_h % 2 != 0: scaled_h -= 1
        pad_y = (H - scaled_h) // 2
        return (f"scale={W}:{scaled_h},"
                f"pad={W}:{H}:0:{pad_y}:black,"
                f"setsar=1,fps={fps}")

# ─────────────────────────────────────────────────────────────────────
#  TEXTES ANIMÉS — 3 NIVEAUX
# ─────────────────────────────────────────────────────────────────────
def write_text_filter(hook, core_text, punchline, total_dur):
    """
    3 couches de texte avec animations distinctes :
    - Hook     : slide depuis le haut, visible 0→2.5s, blanc bold
    - Core     : apparition scale depuis centre, visible 2.5s→5s, blanc semi-transparent
    - Punchline: slide depuis le bas, visible (total-2.8)→fin, jaune bold
    """
    W, H   = [int(x) for x in CFG["resolution"].split("x")]
    fps    = CFG["fps"]
    h_sz   = CFG["hook_size"]
    p_sz   = CFG["punch_size"]
    c_sz   = max(42, p_sz - 12)

    # ── timings ──────────────────────────────
    hook_in    = 0.0
    hook_slide = 0.25
    hook_hold  = 2.2
    hook_out   = 2.5

    core_in    = 2.5
    core_slide = 2.75
    core_hold  = min(5.0, total_dur - 2.5)
    core_out   = min(5.3, total_dur - 2.2)

    pl_in      = max(0.0, total_dur - 2.8)
    pl_slide   = pl_in + 0.25
    pl_out     = total_dur

    # ── positions y ──────────────────────────
    # Zone image (avec padding haut/bas = 160px chacun si ratio < 9:16)
    img_top    = 170   # safe area haut
    img_bottom = H - 170  # safe area bas

    hook_y_final   = img_top + 10
    hook_y_start   = hook_y_final - 120
    pl_y_final     = img_bottom - p_sz - 10
    pl_y_start     = pl_y_final + 120
    core_y         = H // 2 - c_sz // 2

    def ft(t): return f"{t:.3f}"

    # ── HOOK ─────────────────────────────────
    hook_y = (
        f"if(lt(t\\,{ft(hook_slide)})\\,"
        f"{hook_y_start}+(t-{ft(hook_in)})*{int((hook_y_final-hook_y_start)/max(hook_slide-hook_in,0.01))}\\,"
        f"{hook_y_final})"
    )
    hook_alpha = (
        f"if(lt(t\\,{ft(hook_slide)})\\,(t-{ft(hook_in)})/{ft(max(hook_slide-hook_in,0.01))}\\,"
        f"if(lt(t\\,{ft(hook_hold)})\\,1\\,"
        f"max(0\\,({ft(hook_out)}-t)/{ft(max(hook_out-hook_hold,0.01))}))"
        f")"
    )
    hook_filter = (
        f"drawtext=text='{hook}':"
        f"fontfile={FONT}:fontsize={h_sz}:"
        f"fontcolor=white:borderw=8:bordercolor=black:"
        f"x=(w-text_w)/2:y={hook_y}:"
        f"alpha='{hook_alpha}':"
        f"enable='between(t\\,{ft(hook_in)}\\,{ft(hook_out)})'"
    )

    # ── CORE TEXT ────────────────────────────
    core_filter = ""
    if core_text:
        core_alpha = (
            f"if(lt(t\\,{ft(core_slide)})\\,(t-{ft(core_in)})/{ft(max(core_slide-core_in,0.01))}\\,"
            f"if(lt(t\\,{ft(core_hold)})\\,0.85\\,"
            f"max(0\\,({ft(core_out)}-t)/{ft(max(core_out-core_hold,0.01))}))"
            f")"
        )
        core_filter = (
            f",drawtext=text='{core_text}':"
            f"fontfile={FONT}:fontsize={c_sz}:"
            f"fontcolor=white:borderw=5:bordercolor=black:"
            f"x=(w-text_w)/2:y={core_y}:"
            f"alpha='{core_alpha}':"
            f"enable='between(t\\,{ft(core_in)}\\,{ft(core_out)})'"
        )

    # ── PUNCHLINE ────────────────────────────
    pl_alpha = (
        f"if(lt(t\\,{ft(pl_slide)})\\,(t-{ft(pl_in)})/{ft(max(pl_slide-pl_in,0.01))}\\,"
        f"if(lt(t\\,{ft(pl_out-0.3)})\\,1\\,"
        f"max(0\\,({ft(pl_out)}-t)/0.3))"
        f")"
    )
    pl_y = (
        f"if(lt(t\\,{ft(pl_slide)})\\,"
        f"{pl_y_start}-(t-{ft(pl_in)})*{int((pl_y_start-pl_y_final)/max(pl_slide-pl_in,0.01))}\\,"
        f"{pl_y_final})"
    )
    pl_filter = (
        f",drawtext=text='{punchline}':"
        f"fontfile={FONT}:fontsize={p_sz}:"
        f"fontcolor=yellow:borderw=7:bordercolor=black:"
        f"x=(w-text_w)/2:y={pl_y}:"
        f"alpha='{pl_alpha}':"
        f"enable='between(t\\,{ft(pl_in)}\\,{ft(pl_out)})'"
    )

    # ── FOND SEMI-TRANSPARENT (optionnel) ────────────────────────
    bg_filters = ""
    if CFG.get("text_bg"):
        # Bande noire derrière le hook
        bg_filters += (
            f"drawbox=x=0:y={hook_y_final-8}:w=iw:h={h_sz+20}:"
            f"color=black@0.45:t=fill:"
            f"enable='between(t\\,{ft(hook_in)}\\,{ft(hook_out)})',"
        )
        # Bande noire derrière la punchline
        bg_filters += (
            f"drawbox=x=0:y={pl_y_final-8}:w=iw:h={p_sz+20}:"
            f"color=black@0.45:t=fill:"
            f"enable='between(t\\,{ft(pl_in)}\\,{ft(pl_out)})',"
        )
        if core_text:
            bg_filters += (
                f"drawbox=x=0:y={core_y-8}:w=iw:h={c_sz+20}:"
                f"color=black@0.45:t=fill:"
                f"enable='between(t\\,{ft(core_in)}\\,{ft(core_out)})',"
            )

    full_filter = bg_filters + hook_filter + core_filter + pl_filter
    with open("text_filter.txt", "w", encoding="utf-8") as f:
        f.write(full_filter)

def apply_text_overlay(src, out, hook, core_text, punchline):
    dur = get_duration(src)
    write_text_filter(hook, core_text, punchline, dur)
    r = run(f'ffmpeg -y -i "{src}" -filter_script:v text_filter.txt '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print("  ⚠ drawtext échoué — copie sans texte")
        run(f'cp "{src}" "{out}"', silent=True)

# ─────────────────────────────────────────────────────────────────────
#  TRANSITIONS
# ─────────────────────────────────────────────────────────────────────
def make_flash():
    W, H = [int(x) for x in CFG["resolution"].split("x")]
    run(f'ffmpeg -y -f lavfi -i "color=c=white:size={W}x{H}:rate={CFG["fps"]}" '
        f'-t 0.042 -vf "setsar=1" -c:v libx264 -pix_fmt yuv420p flash.mp4')

def best_cut(changes, target, dur, tol=None):
    tol = tol or CFG["tolerance"]
    window = [(t, s) for t, s in changes if abs(t - target) <= tol]
    if window:
        best = max(window, key=lambda x: x[1])
        print(f"  ✓ Cut naturel {best[0]:.3f}s (score {best[1]:.1f})")
        return best[0]
    safe = min(target, dur - 0.15)
    print(f"  ≈ Coupe forcée à {safe:.3f}s")
    return safe

def trim_segment(src, out, duration, vf):
    run(f'ffmpeg -y -i "{src}" -t {duration:.4f} -vf "{vf}" '
        f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')

def apply_zoom_punch(src, out, punch_t):
    """Zoom punch élaboré : accélération non-linéaire + retour élastique."""
    fps        = CFG["fps"]
    scale      = CFG["zoom_scale"]
    pf         = int(punch_t * fps)
    zi, zo     = 3, 8   # frames in / out
    W, H = [int(x) for x in CFG["resolution"].split("x")]

    # Courbe ease-out sur le retour
    zoom_expr = (
        f"if(between(on,{pf},{pf+zi}),"
        f"1.0+(on-{pf})*{scale-1:.3f}/{zi},"
        f"if(between(on,{pf+zi},{pf+zi+zo}),"
        f"{scale:.3f}-({scale-1:.3f})*(on-{pf+zi})/{zo},"
        f"1.0))"
    )
    vf = (
        f"zoompan=z='{zoom_expr}'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d=1:s={W}x{H}:fps={fps}"
    )
    r = run(f'ffmpeg -y -i "{src}" -vf "{vf}" '
            f'-c:v libx264 -preset fast -crf {CFG["crf"]} -an -pix_fmt yuv420p "{out}"')
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        print("  ⚠ zoom échoué — copie directe")
        run(f'cp "{src}" "{out}"', silent=True)

def concat_segments(segments, out):
    with open("list.txt", "w") as f:
        for s in segments:
            f.write(f"file '{s}'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i list.txt '
        f'-c:v libx264 -crf {CFG["crf"]} -preset fast '
        f'-pix_fmt yuv420p -movflags +faststart -an "{out}"')

def merge_audio(video, audio_src, out):
    vid_dur  = get_duration(video)
    fade_dur = CFG["fade_dur"]
    bitrate  = CFG["audio_br"]
    fade_st  = max(0, vid_dur - fade_dur - 0.1)
    run(f'ffmpeg -y -i "{video}" -i "{audio_src}" '
        f'-map 0:v -map 1:a -t {vid_dur:.4f} '
        f'-c:v copy -c:a aac -b:a {bitrate}k '
        f'-af "afade=t=out:st={fade_st:.3f}:d={fade_dur}" '
        f'-movflags +faststart "{out}"')

# ─────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────
def start():
    if not os.path.exists('p.json'):
        print("✗ p.json introuvable"); return

    with open('p.json', 'r') as f:
        data = json.load(f)

    # Appliquer les options depuis p.json
    opts = data.get('options', {})
    for k, v in opts.items():
        if k in CFG:
            CFG[k] = v
    print(f"▶ Config : {CFG['resolution']} {CFG['fps']}fps CRF{CFG['crf']}")

    videos = data.get('videos', [])
    n = len(videos)
    print(f"\n[1/7] Extraction de {n} clip(s)")

    # ── 1. Extraction + analyse ──────────────────────────────────────
    clips_data = []
    for i, v in enumerate(videos):
        path = f"r{i}.mp4"
        with open(path, "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        print(f"\n  Clip r{i}...")
        cd = analyze_clip(path, i)
        print(f"  → {cd['duration']:.2f}s  {cd['width']}x{cd['height']}  "
              f"changes={len(cd['changes'])}  motion={cd['motion']:.1f}  rms={cd['rms']:.0f}dB")
        clips_data.append(cd)

    # ── 2. Ordre narratif ────────────────────────────────────────────
    print(f"\n[2/7] Classification narrative")
    video_roles = data.get('videos', [])
    manual_roles = {v.get('role', 'auto') for v in video_roles}

    if CFG["auto_order"] and manual_roles == {'auto'}:
        roles_order = score_roles(clips_data)
    else:
        # Respecter l'ordre + rôles imposés depuis l'app
        role_map = {'hook': 'hook', 'core': 'core', 'punch': 'punch', 'auto': None}
        roles_order = []
        for i, v in enumerate(video_roles):
            r = role_map.get(v.get('role', 'auto'))
            if r is None:
                r = ['hook', 'core', 'punch'][min(i, 2)]
            roles_order.append((r, clips_data[i]))
        print("  → Ordre manuel respecté")

    durations = []
    for role, _ in roles_order:
        if 'hook_core_punch' in role:
            durations.append(CFG["hook_dur"] + CFG["core_dur"] + CFG["punch_dur"])
        elif role == 'hook':
            durations.append(CFG["hook_dur"])
        elif role == 'core':
            durations.append(CFG["core_dur"])
        else:
            durations.append(CFG["punch_dur"])

    # ── 3. Analyse IA visuelle ───────────────────────────────────────
    print(f"\n[3/7] Analyse IA")
    clips_analysis = None
    if CFG["ai_text"] and API_KEY:
        clips_analysis = ai_analyze_clips(clips_data, roles_order)

    # ── 4. Génération textes ─────────────────────────────────────────
    print(f"\n[4/7] Génération textes")
    if CFG["ai_text"]:
        hook_text, core_text, punch_text = ai_generate_texts(
            clips_analysis, roles_order,
            CFG.get("custom_hook", ""),
            CFG.get("custom_punch", "")
        )
    else:
        hook_text, core_text, punch_text = _default_texts(
            CFG.get("custom_hook", ""), CFG.get("custom_punch", "")
        )

    # ── 5. Découpe + effets ──────────────────────────────────────────
    print(f"\n[5/7] Découpe + effets")
    if CFG["flash_cut"]:
        make_flash()

    segments = []
    for i, ((role, clip), target) in enumerate(zip(roles_order, durations)):
        path    = clip["path"]
        changes = clip["changes"]
        dur     = clip["duration"]
        w, h    = clip["width"], clip["height"]

        cut_t   = best_cut(changes, target, dur)
        vf      = make_vf(w, h)
        raw_seg = f"raw_seg{i}.mp4"
        trim_segment(path, raw_seg, cut_t, vf)

        seg_out = f"seg{i}.mp4"

        # Zoom punch sur le segment CORE au moment le plus intense
        if CFG["zoom_punch"] and role in ('core', 'hook_core_punch'):
            in_seg = [(t, s) for t, s in changes if 0.3 < t < cut_t]
            if in_seg:
                # Choisir le pic d'intensité le plus proche du milieu (plus dramatique)
                mid = cut_t / 2
                pt = max(in_seg, key=lambda x: x[1] * (1 - abs(x[0] - mid) / max(mid, 0.1)))
                print(f"  → Zoom punch r{clip['idx']} à {pt[0]:.3f}s (score {pt[1]:.1f})")
                apply_zoom_punch(raw_seg, seg_out, pt[0])
            else:
                run(f'cp "{raw_seg}" "{seg_out}"', silent=True)
        else:
            run(f'cp "{raw_seg}" "{seg_out}"', silent=True)

        segments.append(seg_out)
        d = get_duration(seg_out)
        print(f"  ✓ Segment {i} ({role}) → {d:.3f}s")

    # ── 6. Assemblage ────────────────────────────────────────────────
    print(f"\n[6/7] Assemblage")
    interleaved = []
    for i, seg in enumerate(segments):
        interleaved.append(seg)
        if i < len(segments) - 1 and CFG["flash_cut"] and os.path.exists("flash.mp4"):
            interleaved.append("flash.mp4")
    concat_segments(interleaved, "no_text.mp4")

    # ── 7. Textes + Audio ────────────────────────────────────────────
    print(f"\n[7/7] Textes + Audio")
    if CFG["ai_text"] or (CFG.get("custom_hook") or CFG.get("custom_punch")):
        print(f"  Textes : '{hook_text}' | '{core_text}' | '{punch_text}'")
        apply_text_overlay("no_text.mp4", "no_audio.mp4", hook_text, core_text, punch_text)
    else:
        run('cp no_text.mp4 no_audio.mp4', silent=True)

    audio_clip = None
    for cd in clips_data:
        has_audio = run(f'ffprobe -v quiet -select_streams a -show_streams "{cd["path"]}"',
                       silent=True).stdout.strip()
        if has_audio:
            audio_clip = cd["path"]; break

    if audio_clip:
        merge_audio("no_audio.mp4", audio_clip, "output.mp4")
    else:
        os.rename("no_audio.mp4", "output.mp4")

    # ── Rapport ──────────────────────────────────────────────────────
    if os.path.exists("output.mp4"):
        fd = get_duration("output.mp4")
        fw, fh = get_dimensions("output.mp4")
        print(f"\n{'='*50}")
        print(f"✅ SUCCÈS  {fw}x{fh}  {fd:.2f}s")
        print(f"   Hook       : {hook_text}")
        if core_text:
            print(f"   Core text  : {core_text}")
        print(f"   Punchline  : {punch_text}")
        print(f"{'='*50}")
    else:
        print("\n❌ ÉCHEC : output.mp4 non généré")

if __name__ == "__main__":
    start()
