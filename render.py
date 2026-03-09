import json, base64, os, subprocess, urllib.request, re

CFG = {"total_dur": 25.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    print(f"Executing: {cmd[:100]}...")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_dynamic_text(frame_b64, step):
    """Génère des mots courts et percutants selon l'image"""
    prompts = [
        "Un mot choc pour le début (ex: STOP, ATTENTION).",
        "Un mot pour décrire ce perso (ex: MONSTRE, GÉNIE).",
        "Une question courte (ex: TU AIMES ?, C'EST QUOI ?).",
        "Un ordre final (ex: ABONNE-TOI, LIKE)."
    ]
    if not GEMINI_KEY: return "CRADOS"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    p = prompts[step] if step < len(prompts) else "INCROYABLE"
    payload = {"contents": [{"parts": [{"text": p}, {"inline_data": {"mime_type": "image/jpeg", "data": frame_b64}}]}]}
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=8) as res:
            raw = json.loads(res.read())['candidates'][0]['content']['parts'][0]['text']
            # Nettoyage ultra-strict pour FFmpeg
            return re.sub(r"[^A-Z ]", "", raw.upper()).strip()[:15]
    except:
        return "VOIR CA"

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips = data.get('videos', [])
    dur = CFG["total_dur"] / len(clips)
    processed_clips = []
    text_filters = []

    for i, v in enumerate(clips):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        # Extraction frame pour l'IA
        run(f'ffmpeg -y -i {raw} -vframes 1 -q:v 2 t{i}.jpg')
        with open(f"t{i}.jpg", "rb") as f: f_b64 = base64.b64encode(f.read()).decode()
        
        # Texte IA ultra-punchy
        txt = get_dynamic_text(f_b64, i)
        
        # Clip fixe (0 zoom)
        out = f"s{i}.mp4"
        run(f'ffmpeg -y -i {raw} -t {dur} -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280" -c:v libx264 -crf 20 {out}')
        processed_clips.append(out)

        # Filtre texte : Apparition brutale ("Pop") au centre
        start_t = i * dur
        end_t = (i + 1) * dur
        # Alternance de couleurs : Blanc et Jaune
        color = "white" if i % 2 == 0 else "yellow"
        
        draw = (f"drawtext=text='{txt}':fontfile={FONT}:fontsize=130:fontcolor={color}:"
                f"borderw=15:bordercolor=black:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,{start_t},{end_t})'")
        text_filters.append(draw)

    # Concaténation
    with open("l.txt", "w") as f:
        for c in processed_clips: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # Finalisation : Textes + Logo + Fade Out
    all_draws = ",".join(text_filters)
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=40:fontcolor=white@0.5:x=w-text_w-40:y=80"
    
    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{all_draws},{brand},fade=t=out:st=24:d=1\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(final_cmd)
    
    if os.path.exists("output.mp4"):
        print("🚀 RÉUSSITE : Vidéo punchy générée.")

if __name__ == "__main__":
    start()
