"""
render.py — ViraCut Les Crados v4.2 (Édition Anti-Crash & Vitalité)
Optimisé pour : TikTok/Shorts/Reels avec fallback automatique si l'IA échoue.
"""
import json, base64, os, subprocess, urllib.request, time, hashlib, random

# ─────────────────────────────────────────────────────────────────────
#  CONFIG VITALITÉ (Boostée pour la rétention)
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "hook_dur": 1.8, "core_dur": 2.2, "punch_dur": 2.8,
    "zoom_scale": 1.15, "ai_text": True, "resolution": "720x1280",
    "fps": 24, "crf": 18, "hook_size": 92, "punch_size": 70,
    "saturation": 1.2, "contrast": 1.1
}

FONT    = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────
#  FONCTIONS DE RENDU
# ─────────────────────────────────────────────────────────────────────
def run(cmd, silent=False):
    if not silent: print(f"  ▸ {cmd[:110]}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_duration(path):
    r = run(f'ffprobe -v quiet -show_entries format=duration -of csv=p=0 "{path}"', silent=True)
    try: return float(r.stdout.strip())
    except: return 0.0

def ai_analyze_and_generate(clips, roles_order):
    """Analyse Vision + Copywriting Viral via Claude"""
    if not API_KEY: return None
    print("\n  [IA] Analyse Vision en cours...")
    content = []
    
    SYSTEM = (
        "Tu es expert TikTok LES CRADOS. Règle : AUCUN caractère spécial (pas d'apostrophe, pas de virgule). "
        "Réponds UNIQUEMENT en JSON strict."
    )

    for role, clip in roles_order[:2]:
        dur = get_duration(clip["path"])
        f_path = f"f_{role}.jpg"
        run(f'ffmpeg -y -ss {dur*0.4} -i "{clip["path"]}" -vframes 1 -q:v 2 "{f_path}"', silent=True)
        if os.path.exists(f_path):
            with open(f_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
                content.append({"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":img_b64}})

    content.append({"type":"text","text": "Génère JSON: {\"hook\":\"TEXTE CHOC\",\"core_text\":\"TEXTE MILIEU\",\"punchline\":\"CHUTE DROLE\"}"})
    
    payload = {
        "model": "claude-3-5-sonnet-20241022", "max_tokens": 300, 
        "messages": [{"role":"user","content":content}], "system": SYSTEM
    }
    
    try:
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode(),
                                     headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read())
            return json.loads(data["content"][0]["text"])
    except Exception as e:
        print(f"  ⚠ Erreur API Claude : {e}")
        return None

def apply_ultra_text(src, out, texts):
    """Incrustation des textes avec animations agressives"""
    dur = get_duration(src)
    # Protection contre le crash NoneType
    h = texts.get('hook','ATTENDS').replace("'","")
    c = texts.get('core_text','INCROYABLE').replace("'","")
    p = texts.get('punchline','FINI').replace("'","")
    
    # Hook: Pop 0.1s | Punch: Shake 90Hz
    vf = (
        f"drawtext=text='{h}':fontfile={FONT}:fontsize={CFG['hook_size']}:fontcolor=#FF2D55:borderw=10:bordercolor=black:"
        f"x=(w-text_w)/2:y=120:alpha='if(lt(t,0.1),t/0.1,if(lt(t,1.5),1,max(0,1-(t-1.5)/0.3)))':enable='between(t,0,1.8)',"
        f"drawtext=text='{p}':fontfile={FONT}:fontsize={CFG['punch_size']}:fontcolor=#FFE600:borderw=10:bordercolor=black:"
        f"x='(w-text_w)/2+10*sin(t*90)':y=h-220:enable='between(t,{dur-2.5},{dur})',"
        f"eq=contrast={CFG['contrast']}:saturation={CFG['saturation']}"
    )
    run(f'ffmpeg -y -i "{src}" -vf "{vf}" -c:v libx264 -crf {CFG["crf"]} -pix_fmt yuv420p "{out}"')

# ─────────────────────────────────────────────────────────────────────
#  START (Pipeline Principal)
# ─────────────────────────────────────────────────────────────────────
def start():
    if not os.path.exists('p.json'):
        print("✗ p.json introuvable"); return

    with open('p.json') as f: data = json.load(f)
    videos = data.get('videos', [])
    
    # 1. Extraction
    clips = []
    for i, v in enumerate(videos):
        path = f"r{i}.mp4"
        with open(path, "wb") as fout: fout.write(base64.b64decode(v['data']))
        clips.append({"path": path, "idx": i})

    # 2. IA Vision + Fallback Sécurisé
    roles_order = [("hook", clips[0]), ("punch", clips[-1])]
    texts = None
    if API_KEY:
        texts = ai_analyze_and_generate(clips, roles_order)
    
    if texts is None:
        print("  ⚠ Fallback activé : Textes par défaut générés.")
        texts = {"hook": "ATTENDS LA FIN", "core_text": "C EST QUOI CA", "punchline": "ABONNE TOI POUR PLUS"}

    # 3. Montage Agressif
    print("[Rendu] Montage et effets de vitalité...")
    # Montage simplifié en 2 segments pour la rapidité
    seg1, seg2 = "s1.mp4", "s2.mp4"
    run(f'ffmpeg -y -i {clips[0]["path"]} -t {CFG["hook_dur"]} -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280" {seg1}')
    run(f'ffmpeg -y -i {clips[-1]["path"]} -t {CFG["punch_dur"]} -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280" {seg2}')
    
    # Fusion sans texte
    run(f'ffmpeg -y -i {seg1} -i {seg2} -filter_complex "[0:v][1:v]concat=n=2:v=1:a=0" no_text.mp4')
    
    # 4. Habillage Final
    apply_ultra_text("no_text.mp4", "output.mp4", texts)
    print("\n✅ SUCCÈS : output.mp4 prêt pour la vitalité.")

if __name__ == "__main__":
    start()
