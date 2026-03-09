import json, base64, os, subprocess, urllib.request, re

CFG = {"total_dur": 25.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_clip_text(frame_b64, index):
    """Demande à Gemini un texte spécifique pour CHAQUE clip"""
    if not GEMINI_KEY: return "IMAGE INCROYABLE"
    
    prompts = [
        "Trouve un HOOK (3 mots) pour ce perso Crados.",
        "Décris son équipement Steampunk (3 mots).",
        "Pose une question sur son regard (3 mots).",
        "Fais un appel à l'action (Like/Abonne-toi)."
    ]
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    p = prompts[index] if index < len(prompts) else prompts[-1]
    payload = {"contents": [{"parts": [{"text": p}, {"inline_data": {"mime_type": "image/jpeg", "data": frame_b64}}]}]}
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as res:
            raw = json.loads(res.read())['candidates'][0]['content']['parts'][0]['text']
            return re.sub(r"[^a-zA-Z0-9 !?À-ÿ]", "", raw).strip().upper()
    except:
        return "REGARDE CA"

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips_data = data.get('videos', [])
    num_clips = len(clips_data)
    dur_segment = CFG["total_dur"] / num_clips
    
    segments = []
    text_filters = []
    current_time = 0

    for i, v in enumerate(clips_data):
        raw_p = f"r{i}.mp4"
        with open(raw_p, "wb") as f: f.write(base64.b64decode(v['data']))
        
        # 1. Extraction d'une image pour Gemini
        run(f'ffmpeg -y -i {raw_p} -vframes 1 -f image2 pipe:1 > t{i}.jpg')
        with open(f"t{i}.jpg", "rb") as f: f_b64 = base64.b64encode(f.read()).decode()
        
        # 2. Récupération du texte contextuel
        txt = get_clip_text(f_b64, i)
        
        # 3. Préparation du segment (Zoom 1.05 constant pour la sécurité)
        out_p = f"s{i}.mp4"
        vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,scale=iw*1.05:-1,crop=720:1280"
        run(f'ffmpeg -y -i {raw_p} -t {dur_segment} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac {out_p}')
        segments.append(out_p)

        # 4. Création du filtre de texte synchronisé
        draw = f"drawtext=text='{txt}':fontfile={FONT}:borderw=10:bordercolor=black:fontcolor=white:fontsize=85:x=(w-text_w)/2:y=h/2:enable='between(t,{current_time},{current_time + dur_segment})'"
        text_filters.append(draw)
        current_time += dur_segment

    # 5. Assemblage final
    with open("l.txt", "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # Ajout des textes + Watermark + Fade Out
    filters = ",".join(text_filters)
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=35:fontcolor=white@0.6:x=w-text_w-50:y=120"
    
    cmd_final = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},{filters},fade=t=out:st={CFG['total_dur']-1}:d=1\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(cmd_final)
    print("✅ Rendu v15 terminé : Textes contextuels et synchro parfaite.")

if __name__ == "__main__":
    start()
