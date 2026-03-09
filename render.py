import json, base64, os, subprocess, urllib.request, time, re

# ─────────────────────────────────────────────────────────────────────
#  CONFIG DYNAMIQUE
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "total_dur": 25.0,
    "fps": 24,
    "res": "720:1280",
    "zoom": 0.0012, # Zoom fluide
    "crf": 18
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    print(f"  ▸ Exécution FFmpeg...")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0: print(f"  ❌ FFmpeg Error: {r.stderr[:300]}")
    return r

def clean(t):
    """Bouclier anti-crash : élimine tout caractère risqué pour FFmpeg"""
    if not t: return ""
    # On garde lettres, chiffres et espaces uniquement
    t = re.sub(r"[^a-zA-Z0-9 !?]", "", t)
    return t.strip().upper()

def get_gemini_punch(frame_b64):
    """Gemini génère le scénario texte et la couleur"""
    if not GEMINI_KEY:
        return {"h": "NE SWIPE PAS", "m": "REGARDE CA", "p": "ABONNE TOI", "c": "yellow"}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = (
        "Analyse cette carte Les Crados. Crée 3 textes courts et percutants : "
        "1. HOOK (Capture l'attention), 2. MID (Description drôle), 3. PUNCH (Chute). "
        "Choisis une couleur vive (HEX) pour le texte. "
        "RÉPONSES SANS GUILLEMETS NI DEUX-POINTS. "
        "JSON: {\"h\": \"...\", \"m\": \"...\", \"p\": \"...\", \"c\": \"#HEX\"}"
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": frame_b64}}]}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as res:
            raw = json.loads(res.read())['candidates'][0]['content']['parts'][0]['text']
            data = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
            return { "h": clean(data['h']), "m": clean(data['m']), "p": clean(data['p']), "c": data.get('c', 'yellow') }
    except:
        return {"h": "INCROYABLE", "m": "REGARDE BIEN", "p": "ABONNE TOI", "c": "yellow"}

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction & Thumbnail
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"raw_{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)
    
    run(f'ffmpeg -y -i {clips[0]} -ss 1 -vframes 1 thumb.jpg')
    with open("thumb.jpg", "rb") as f: f_b64 = base64.b64encode(f.read()).decode()

    # 2. IA Gemini
    ai = get_gemini_punch(f_b64)

    # 3. Segments (Format 9:16 + Zoompan stable)
    dur = CFG["total_dur"] / len(clips)
    segs = []
    vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"
    # S=720x1280 est CRUCIAL pour éviter le crash du zoompan
    zp = f"zoompan=z='min(zoom+{CFG['zoom']},1.2)':d=1:s=720x1280:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    for i, cp in enumerate(clips):
        out = f"s{i}.mp4"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf},{zp}" -c:v libx264 -c:a aac -ar 44100 s{i}.mp4')
        segs.append(out)

    # 4. Montage Final avec Textes Punchy
    with open("l.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")

    # On définit les timings pour que les textes "débarquent"
    draw = f"fontfile={FONT}:borderw=6:bordercolor=black:x=(w-text_w)/2"
    
    cmd_final = (
        f"ffmpeg -y -f concat -i l.txt -vf "
        f"\"drawtext=text='{ai['h']}':{draw}:fontsize=90:fontcolor=white:y=250:enable='between(t,0,4)', "
        f"drawtext=text='{ai['m']}':{draw}:fontsize=80:fontcolor={ai['c']}:y=h/2-100:enable='between(t,5,10)', "
        f"drawtext=text='IDENTIFIE UN POTE':{draw}:fontsize=60:fontcolor=yellow:y=h/2+100:enable='between(t,12,17)', "
        f"drawtext=text='LIKE ET ABONNE TOI':{draw}:fontsize=70:fontcolor=white:y=h-300:enable='between(t,18,25)'\" "
        f"-c:v libx264 -crf 18 -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    if os.path.exists("output.mp4"): print("✅ SUCCESS")

if __name__ == "__main__":
    start()
