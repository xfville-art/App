import json, base64, os, subprocess, urllib.request, time, re

# ─────────────────────────────────────────────────────────────────────
#  CONFIG GEMINI & VITALITÉ
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "total_target_dur": 25.0,
    "fps": 24,
    "zoom_speed": 0.0012,
    "crf": 18
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
# Pense à ajouter GEMINI_API_KEY dans tes secrets GitHub
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def clean_text(t):
    """Bouclier anti-crash : supprime : " ' et garde l'essentiel"""
    if not t: return ""
    t = t.replace(":", " ").replace('"', " ").replace("'", " ")
    t = re.sub(r"[^a-zA-Z0-9 !?À-ÿ]", "", t)
    return t.strip().upper()

def get_gemini_creative(frame_b64):
    """Appel à Gemini 1.5 Flash pour le texte et la couleur"""
    if not GEMINI_KEY:
        return {"h": "TAS VU CA ?", "p": "ABONNE TOI", "c": "#FFFF00"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt = (
        "Analyse cette carte Les Crados. "
        "1. Crée un HOOK viral et une PUNCHLINE drôle. "
        "2. Choisis une COULEUR HEXADÉCIMALE vive (fluo) présente sur l'image pour le texte. "
        "Interdiction de mettre des guillemets ou deux-points. "
        "Réponds UNIQUEMENT en JSON : {\"hook\": \"...\", \"punch\": \"...\", \"color\": \"#RRGGBB\"}"
    )

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": frame_b64}}
            ]
        }]
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read())
            raw = res['candidates'][0]['content']['parts'][0]['text']
            # Extraction propre du JSON
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(match.group())
            return {
                "h": clean_text(data.get("hook", "INCROYABLE")),
                "p": clean_text(data.get("punch", "SUITE BIENTOT")),
                "c": data.get("color", "#FFFF00") # Jaune par défaut
            }
    except:
        return {"h": "REGARDE BIEN", "p": "ABONNE TOI", "c": "#FFFF00"}

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction et Frame pour l'IA
    vids = data.get('videos', [])
    clips = []
    for i, v in enumerate(vids):
        p = f"raw_{i}.mp4"; f_b64 = ""
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)
    
    # On prend une frame au milieu du premier clip pour Gemini
    run(f'ffmpeg -y -i {clips[0]} -ss 1 -vframes 1 -q:v 2 thumb.jpg')
    with open("thumb.jpg", "rb") as f: f_b64 = base64.b64encode(f.read()).decode()

    # 2. Intelligence Artificielle Gemini
    idea = get_gemini_creative(f_b64)
    print(f"✨ Gemini suggère : {idea['h']} avec la couleur {idea['c']}")

    # 3. Préparation des segments (9:16 + Zoom)
    num = len(clips)
    dur = CFG["total_target_dur"] / num
    segs = []
    vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"
    zoom = f"zoompan=z='min(zoom+{CFG['zoom_speed']},1.3)':d=1:s=720x1280:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    for i, cp in enumerate(clips):
        out = f"seg_{i}.mp4"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf},{zoom}" -c:v libx264 -c:a aac -ar 44100 -ac 2 {out}')
        segs.append(out)

    # 4. Assemblage Final
    with open("list.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")

    cmd_final = (
        f"ffmpeg -y -f concat -i list.txt -vf "
        f"\"drawtext=text='{idea['h']}':fontfile={FONT}:fontsize=80:fontcolor={idea['c']}:borderw=6:bordercolor=black:x=(w-text_w)/2:y=200:enable='between(t,0,6)', "
        f"drawtext=text='{idea['p']}':fontfile={FONT}:fontsize=65:fontcolor={idea['c']}:borderw=6:bordercolor=black:x=(w-text_w)/2:y=h-300:enable='between(t,{CFG['total_target_dur']-7},{CFG['total_target_dur']})'\" "
        f"-c:v libx264 -crf {CFG['crf']} -c:a aac -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    if os.path.exists("output.mp4"): print("✅ Rendu Gemini terminé.")

if __name__ == "__main__":
    start()
