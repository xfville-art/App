import json, base64, os, subprocess, urllib.request, re

CFG = {"total_dur": 25.0, "fps": 24, "res": "720:1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def safe_txt(t):
    return re.sub(r"[^a-zA-Z0-9 !?À-ÿ]", "", t).strip().upper()

def get_ai_data(frame_b64):
    if not GEMINI_KEY:
        return {"h": "STOP !", "m": "REGARDE CA", "p": "INCROYABLE", "c": "yellow"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = "Donne 3 textes courts (3 mots max) pour une vidéo virale. JSON: {\"h\": \"...\", \"m\": \"...\", \"p\": \"...\", \"c\": \"#HEX\"}"
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": frame_b64}}]}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as res:
            raw = json.loads(res.read())['candidates'][0]['content']['parts'][0]['text']
            js = json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group())
            return {k: safe_txt(v) if k != 'c' else v for k, v in js.items()}
    except:
        return {"h": "NE SWIPE PAS", "m": "T'AS VU CA ?", "p": "ABONNE-TOI", "c": "white"}

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
    ai = get_ai_data(f_b64)

    # 2. Montage des Segments avec "Jump Zooms" (Effet nerveux)
    # On alterne entre zoom 1.0, 1.2 et 1.1 pour simuler un montage pro
    segs = []
    dur = CFG["total_dur"] / len(clips)
    zooms = ["1.0", "1.2", "1.1", "1.3"]
    
    for i, cp in enumerate(clips):
        out = f"s{i}.mp4"
        z = zooms[i % len(zooms)]
        # Plus robuste que zoompan : scale + crop simple
        vf = f"scale=1280:1280,crop=720:1280,scale=iw*{z}:ih*{z},crop=720:1280"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf}" -c:v libx264 -c:a aac -ar 44100 {out}')
        segs.append(out)

    # 3. Assemblage Final
    with open("l.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # 4. Textes Punchy (Incrustation simplifiée pour éviter le crash)
    draw = f"fontfile={FONT}:borderw=10:bordercolor=black:x=(w-text_w)/2"
    
    cmd_final = (
        f"ffmpeg -y -i base.mp4 -vf "
        f"\"drawtext=text='{ai['h']}':{draw}:fontsize=120:fontcolor=white:y=250:enable='between(t,0,4)', "
        f"drawtext=text='{ai['m']}':{draw}:fontsize=100:fontcolor={ai['c']}:y=h/2:enable='between(t,6,12)', "
        f"drawtext=text='LIKE ET COMMENTE':{draw}:fontsize=80:fontcolor=yellow:y=h-450:enable='between(t,15,20)', "
        f"drawtext=text='{ai['p']}':{draw}:fontsize=95:fontcolor=white:y=h-250:enable='between(t,21,25)'\" "
        f"-c:v libx264 -crf 20 -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    print("✅ Rendu terminé.")

if __name__ == "__main__":
    start()
