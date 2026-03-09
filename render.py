"""
render.py — ViraCut Les Crados v4.1 (Édition Vitalité Max)
Pipeline : Extraction → Analyse Vision (Claude) → Montage Agressif → Textes Animés
"""
import json, base64, os, subprocess, urllib.request, time, hashlib, random

# ─────────────────────────────────────────────────────────────────────
#  CONFIG VITALITÉ (Boostée pour TikTok/Reels)
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "hook_dur": 1.8, "core_dur": 2.2, "punch_dur": 2.8, # Durées plus courtes pour le rythme
    "tolerance": 0.8, "flash_cut": True, "zoom_punch": True,
    "zoom_scale": 1.15, "ai_text": True, "auto_order": True,
    "resolution": "720x1280", "fps": 24, "crf": 18,
    "hook_size": 92, "punch_size": 70, "text_bg": False,
    "saturation": 1.2, "contrast": 1.1 # Color grading intégré
}

FONT    = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "") # Secret Token

# ─────────────────────────────────────────────────────────────────────
#  SYSTÈME DE RENDU OPTIMISÉ
# ─────────────────────────────────────────────────────────────────────
def run(cmd, silent=False):
    if not silent: print(f"  ▸ {cmd[:110]}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_duration(path):
    r = run(f'ffprobe -v quiet -show_entries format=duration -of csv=p=0 "{path}"', silent=True)
    return float(r.stdout.strip() or 0)

# ── IA VISION : Analyse des cartes pour copywriting contextuel ──
def ai_analyze_and_generate(clips_data, roles_order):
    print("\n  [IA] Analyse Vision + Copywriting Viral...")
    content = []
    
    # Système Prompt "Secret" pour la vitalité
    SYSTEM = (
        "Tu es un expert TikTok pour LES CRADOS. Ton but : RETENTION MAXIMALE. "
        "Analyse les noms sur les cartes et crée un HOOK choc, un CORE cynique et une PUNCHLINE absurde. "
        "IMPORTANT : Aucun caractère spécial (pas d'apostrophe, ni virgule, ni emoji complexe)."
    )

    # Extraction des frames pour l'IA
    for role, clip in roles_order[:2]: # On analyse les 2 clips principaux
        dur = get_duration(clip["path"])
        frame_path = f"analyze_{role}.jpg"
        run(f'ffmpeg -y -ss {dur*0.5} -i "{clip["path"]}" -vframes 1 -q:v 2 "{frame_path}"', silent=True)
        if os.path.exists(frame_path):
            with open(frame_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
                content.append({"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":img_b64}})

    content.append({"type":"text","text": "Génère JSON: {\"hook\":\"...\",\"core_text\":\"...\",\"punchline\":\"...\"}"})
    
    # Appel API avec Token Secret
    payload = {"model": "claude-3-5-sonnet-20241022", "max_tokens": 300, "messages": [{"role":"user","content":content}], "system": SYSTEM}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode(),
                                 headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return json.loads(data["content"][0]["text"])
    except: return None

# ── TEXTES ANIMÉS (Pop $0.1s$ / Shake $90Hz$) ──
def apply_ultra_text(src, out, texts):
    dur = get_duration(src)
    h, c, p = texts.get('hook',''), texts.get('core_text',''), texts.get('punchline','')
    
    # Filtres FFmpeg complexes pour le dynamisme
    # Hook: Pop en 0.1s | Punch: Shake 90Hz
    vf = (
        f"drawtext=text='{h}':fontfile={FONT}:fontsize={CFG['hook_size']}:fontcolor=#FF2D55:borderw=8:x=(w-text_w)/2:y=120:"
        f"alpha='if(lt(t,0.1),t/0.1,if(lt(t,1.5),1,max(0,1-(t-1.5)/0.3)))':enable='between(t,0,1.8)',"
        f"drawtext=text='{p}':fontfile={FONT}:fontsize={CFG['punch_size']}:fontcolor=#FFE600:borderw=8:"
        f"x='(w-text_w)/2+10*sin(t*90)':y=h-200:enable='between(t,{dur-2.5},{dur})'"
    )
    
    # Color Grading + Textes
    run(f'ffmpeg -y -i "{src}" -vf "{vf},eq=contrast={CFG["contrast"]}:saturation={CFG["saturation"]}" -c:v libx264 -crf 18 "{out}"')

# ─────────────────────────────────────────────────────────────────────
#  MAIN EXECUTION
# ─────────────────────────────────────────────────────────────────────
def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Préparation des clips
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        path = f"r{i}.mp4"
        with open(path, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append({"path": path, "idx": i})

    # 2. IA Vision (Si Token présent)
    roles = [("hook", clips[0]), ("punch", clips[-1])]
    texts = ai_analyze_and_generate(clips, roles) if API_KEY else {"hook": "ATTENDS LA FIN", "punch": "ABONNE TOI"}

    # 3. Montage & Textes
    print("[Rendu] Montage agressif en cours...")
    # (Logique simplifiée pour l'exemple de rendu final)
    run(f'ffmpeg -y -i {clips[0]["path"]} -t {CFG["hook_dur"]} -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280" hook_tmp.mp4')
    run(f'ffmpeg -y -i {clips[-1]["path"]} -t {CFG["punch_dur"]} -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280" punch_tmp.mp4')
    
    # Concaténation + Textes Viraux
    run(f'ffmpeg -y -i hook_tmp.mp4 -i punch_tmp.mp4 -filter_complex "[0:v][1:v]concat=n=2:v=1:a=0" no_text.mp4')
    apply_ultra_text("no_text.mp4", "output.mp4", texts)
    
    print(f"\n✅ Rendu Terminé : output.mp4 généré avec succès.")

if __name__ == "__main__":
    start()
