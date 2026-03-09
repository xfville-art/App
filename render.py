import json, base64, os, subprocess, urllib.request, time, re

# ─────────────────────────────────────────────────────────────────────
#  CONFIG DYNAMIQUE & RÉTENTION
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "total_dur": 25.0,
    "fps": 24,
    "res": "720:1280",
    "zoom_speed": 0.002, # Zoom plus nerveux pour le dynamisme
    "crf": 18
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def clean(t):
    """Nettoyage strict pour éviter les crashs FFmpeg"""
    if not t: return ""
    t = re.sub(r"[^a-zA-Z0-9 !?À-ÿ]", "", t)
    return t.strip().upper()

def get_gemini_data(frame_b64):
    """Analyse Vision + Scripting Viral"""
    if not GEMINI_KEY:
        return {"h": "NE SWIPE PAS", "m": "C'EST INCROYABLE", "p": "ABONNE-TOI", "c": "#FF00FF"}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = (
        "Tu es un monteur vidéo viral. Analyse cette image 'Les Crados'. "
        "Génère 3 textes : 1 HOOK (0-4s), 1 DESCRIPTION (5-12s), 1 PUNCHLINE (18-25s). "
        "Choisis une COULEUR HEX vive présente dans l'image. "
        "PAS DE : NI DE \". RÉPONSE JSON UNIQUEMENT : "
        "{\"h\": \"TEXTE\", \"m\": \"TEXTE\", \"p\": \"TEXTE\", \"c\": \"#HEX\"}"
    )
    
    data = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": frame_b64}}]}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=12) as res:
            raw = json.loads(res.read())['candidates'][0]['content']['parts'][0]['text']
            js = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
            return { "h": clean(js['h']), "m": clean(js['m']), "p": clean(js['p']), "c": js.get('c', '#FFFF00') }
    except:
        return {"h": "REGARDE BIEN", "m": "C'EST FOU", "p": "SUITE BIENTÔT", "c": "#FFFF00"}

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction et Analyse Image
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)
    
    run(f'ffmpeg -y -i {clips[0]} -ss 1 -vframes 1 thumb.jpg')
    with open("thumb.jpg", "rb") as f: f_b64 = base64.b64encode(f.read()).decode()
    ai = get_gemini_data(f_b64)

    # 2. Préparation des segments (Zoom & Portrait)
    segs = []
    dur = CFG["total_dur"] / len(clips)
    vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"
    zp = f"zoompan=z='min(zoom+{CFG['zoom_speed']},1.4)':d=1:s=720x1280:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    for i, cp in enumerate(clips):
        out = f"s{i}.mp4"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf},{zp}" -c:v libx264 -c:a aac -ar 44100 s{i}.mp4')
        segs.append(out)

    # 3. Montage Final avec Textes Punchy (Effet Pop)
    with open("list.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")

    # Filtre de texte avec animations de timing
    draw = f"fontfile={FONT}:borderw=8:bordercolor=black:x=(w-text_w)/2"
    
    cmd_final = (
        f"ffmpeg -y -f concat -i list.txt -vf "
        f"\"drawtext=text='{ai['h']}':{draw}:fontsize=110:fontcolor=white:y=250:enable='between(t,0,4)', "
        f"drawtext=text='{ai['m']}':{draw}:fontsize=85:fontcolor={ai['c']}:y=h/2:enable='between(t,5,12)', "
        f"drawtext=text='IDENTIFIE UN POTE':{draw}:fontsize=70:fontcolor=white:y=h/2+150:enable='between(t,14,19)', "
        f"drawtext=text='LIKE ET ABONNE-TOI':{draw}:fontsize=80:fontcolor=yellow:y=h-300:enable='between(t,20,25)'\" "
        f"-c:v libx264 -crf 18 -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    if os.path.exists("output.mp4"): print("✅ Rendu Viral Terminé")

if __name__ == "__main__":
    start()
