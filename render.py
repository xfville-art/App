import json, base64, os, subprocess, urllib.request, time, re

CFG = {"total_dur": 25.0, "fps": 24, "res": "720x1280", "crf": 18}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    print(f"  ▸ Exécution FFmpeg...")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0: print(f"  ❌ Erreur: {r.stderr[:200]}")
    return r

def safe_txt(t):
    """Purge totale des caractères qui font crash FFmpeg"""
    return re.sub(r"[^a-zA-Z0-9 !?À-ÿ]", "", t).strip().upper()

def get_ai_content(frame_b64):
    """Demande à Gemini des textes ultra-courts pour le dynamisme"""
    if not GEMINI_KEY:
        return {"h": "C'EST FOU", "m": "REGARDE BIEN", "p": "ABONNE-TOI", "c": "yellow"}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = (
        "Crée 3 phrases chocs pour une vidéo virale (2-3 mots max chacune). "
        "1. HOOK, 2. INSCRIPTION, 3. PUNCHLINE. "
        "Donne aussi une couleur HEX vive. JSON UNIQUEMENT : "
        "{\"h\": \"...\", \"m\": \"...\", \"p\": \"...\", \"c\": \"#HEX\"}"
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": frame_b64}}]}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as res:
            raw = json.loads(res.read())['candidates'][0]['content']['parts'][0]['text']
            js = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
            return {k: safe_txt(v) if k != 'c' else v for k, v in js.items()}
    except:
        return {"h": "INCROYABLE", "m": "REGARDE CA", "p": "SUITE ICI", "c": "yellow"}

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Analyse Image
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)
    
    run(f'ffmpeg -y -i {clips[0]} -vframes 1 t.jpg')
    with open("t.jpg", "rb") as f: f_b64 = base64.b64encode(f.read()).decode()
    ai = get_ai_content(f_b64)

    # 2. Rendu des Segments avec Zoom Progressif (simule ton exemple)
    segs = []
    dur = CFG["total_dur"] / len(clips)
    for i, cp in enumerate(clips):
        out = f"s{i}.mp4"
        # Filtre : Zoom lent + Cadrage 9:16
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,zoompan=z='zoom+0.001':d=1:s=720x1280"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf}" -c:v libx264 -c:a aac -ar 44100 {out}')
        segs.append(out)

    # 3. Montage Final avec Textes "Punchy"
    with open("l.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # Filtres de texte dynamiques
    # h = Hook (0-4s) / m = Milieu (6-12s) / CTA (15-20s) / p = Fin (21-25s)
    draw = f"fontfile={FONT}:borderw=10:bordercolor=black:x=(w-text_w)/2"
    
    cmd_final = (
        f"ffmpeg -y -i base.mp4 -vf "
        f"\"drawtext=text='{ai['h']}':{draw}:fontsize=110:fontcolor=white:y=250:enable='between(t,0,4)', "
        f"drawtext=text='{ai['m']}':{draw}:fontsize=90:fontcolor={ai['c']}:y=h/2:enable='between(t,6,12)', "
        f"drawtext=text='LIKE ET COMMENTE':{draw}:fontsize=70:fontcolor=yellow:y=h-450:enable='between(t,15,20)', "
        f"drawtext=text='{ai['p']}':{draw}:fontsize=90:fontcolor=white:y=h-250:enable='between(t,21,25)'\" "
        f"-c:v libx264 -crf 18 -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    if os.path.exists("output.mp4"): print("✅ RENDU VIRAL OK")

if __name__ == "__main__":
    start()
