import json, base64, os, subprocess, urllib.request, time, re

# ─────────────────────────────────────────────────────────────────────
#  PARAMÈTRES DE RENDU VIRAL
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "total_dur": 25.0,
    "fps": 24,
    "res": "720x1280",
    "crf": 18
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    print(f"  ▸ FFmpeg en cours...")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0: print(f"  ❌ Erreur: {r.stderr[:200]}")
    return r

def clean(t):
    if not t: return ""
    # On autorise uniquement Alphanumérique et les points d'exclamation
    t = re.sub(r"[^a-zA-Z0-9 !?À-ÿ]", "", t)
    return t.strip().upper()

def get_gemini_punch(frame_b64):
    if not GEMINI_KEY:
        return {"h": "NE REGARDE PAS", "m": "C'EST HORRIBLE", "p": "ABONNE TOI", "c": "yellow"}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = (
        "Analyse cette image Crados. "
        "Génère 3 textes courts (4 mots max) : 1 HOOK, 1 DESCRIPTION, 1 PUNCHLINE. "
        "Choisis une couleur HEX vive. "
        "IMPORTANT: AUCUN CARACTERE SPECIAL (pas de : ni \"). "
        "JSON: {\"h\": \"...\", \"m\": \"...\", \"p\": \"...\", \"c\": \"#HEX\"}"
    )
    
    data = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": frame_b64}}]}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=12) as res:
            raw = json.loads(res.read())['candidates'][0]['content']['parts'][0]['text']
            js = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
            return { "h": clean(js['h']), "m": clean(js['m']), "p": clean(js['p']), "c": js.get('c', 'yellow') }
    except:
        return {"h": "C'EST FOU", "m": "REGARDE CA", "p": "ABONNE TOI", "c": "yellow"}

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction et Analyse Gemini
    clips_raw = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips_raw.append(p)
    
    run(f'ffmpeg -y -i {clips_raw[0]} -vframes 1 t.jpg')
    with open("t.jpg", "rb") as f: f_b64 = base64.b64encode(f.read()).decode()
    ai = get_gemini_punch(f_b64)

    # 2. Création des segments avec ZOOM DYNAMIQUE (Effet "Punch")
    dur = CFG["total_dur"] / len(clips_raw)
    segs = []
    # On alterne le zoom entre chaque segment pour créer une cassure visuelle (Jump Cut)
    for i, cp in enumerate(clips_raw):
        out = f"s{i}.mp4"
        z_val = "1.1+0.2*sin(t*2)" # Zoom qui pulse légèrement
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,zoompan=z='{z_val}':d=1:s=720x1280"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf}" -c:v libx264 -c:a aac -ar 44100 s{i}.mp4')
        segs.append(out)

    # 3. Assemblage intermédiaire
    with open("l.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy tmp.mp4")

    # 4. INCROSTATION TEXTE PUNCHY (Le moment où ça débarque)
    # Style: Ombre portée, tremblement sur le CTA
    draw = f"fontfile={FONT}:borderw=8:bordercolor=black:x=(w-text_w)/2"
    
    # On ajoute un effet 'shake' (tremblement) aléatoire sur le texte du milieu
    shake_y = "y=h/2+(5*sin(t*50))" 

    cmd_final = (
        f"ffmpeg -y -i tmp.mp4 -vf "
        f"\"drawtext=text='{ai['h']}':{draw}:fontsize=110:fontcolor=white:y=200:enable='between(t,0,4)', "
        f"drawtext=text='{ai['m']}':{draw}:fontsize=90:fontcolor={ai['c']}:{shake_y}:enable='between(t,6,12)', "
        f"drawtext=text='LIKE ET COMMENTE':{draw}:fontsize=75:fontcolor=yellow:y=h-450:enable='between(t,15,20)', "
        f"drawtext=text='{ai['p']}':{draw}:fontsize=80:fontcolor=white:y=h-250:enable='between(t,21,25)'\" "
        f"-c:v libx264 -crf 18 -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    if os.path.exists("output.mp4"): print("✅ RENDU VIRAL RÉUSSI")

if __name__ == "__main__":
    start()
