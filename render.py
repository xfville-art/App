import json, base64, os, subprocess, requests

# CONFIGURATION
CFG = {
    "res": "720x1280",
    "fps": 24,
    "text_size": 45,
    "watermark": "@LesCrados.ai",
    "api_key": os.getenv("GEMINI_API_KEY") # À configurer dans GitHub Secrets
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def ask_gemini(prompt):
    """Génère une punchline courte via l'API Gemini"""
    if not CFG["api_key"]:
        return "MUTATION GENERALE" # Fallback si pas de clé
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={CFG['api_key']}"
    payload = {
        "contents": [{
            "parts": [{"text": f"Génère une seule punchline très courte (max 3 mots), provocatrice, dégoûtante et drôle dans l'univers des 'Crados' pour cette vidéo : {prompt}. Réponds uniquement avec la punchline, sans ponctuation inutile."}]
        }]
    }
    try:
        r = requests.post(url, json=payload)
        return r.json()['candidates'][0]['content']['parts'][0]['text'].upper().strip()
    except:
        return "HORREUR IA"

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    processed = []
    dynamic_texts = []
    
    # 1. GÉNÉRATION DES TEXTES ET NORMALISATION
    for i, v in enumerate(videos):
        # On demande à Gemini une phrase unique pour ce clip
        # On peut passer le prompt original de l'IA s'il est dans le JSON, sinon un thème par défaut
        desc = v.get('prompt', 'un monstre dégoûtant et rigolo')
        punchline = ask_gemini(desc)
        dynamic_texts.append(punchline)
        print(f"Clip {i} : {punchline}")

        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"seg_{i}.mp4"
        
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']}"
        cmd = (f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo '
               f'-filter_complex "[0:v]{vf}[v];[0:a][1:a]amix=inputs=2:duration=first[a]" '
               f'-map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac -ar 44100 {out}')
        subprocess.run(cmd, shell=True)
        processed.append(out)

    # 2. CONCATÉNATION
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    subprocess.run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base.mp4", shell=True)

    # 3. SCRIPT DE FILTRES AVEC TEXTES IA
    res = subprocess.run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 base.mp4", 
                         shell=True, capture_output=True, text=True)
    total_dur = float(res.stdout.strip())
    dur_seg = total_dur / len(processed)

    with open("myscript.txt", "w") as f:
        # Watermark
        f.write(f"drawtext=text='{CFG['watermark']}':fontfile={FONT}:fontsize=22:fontcolor=white@0.3:x=w-text_w-40:y=60,")
        
        filters = []
        for i, txt in enumerate(dynamic_texts):
            t_start = i * dur_seg
            t_end = (i + 1) * dur_seg
            # Nettoyage pour éviter les erreurs FFmpeg
            clean_txt = txt.replace("'", "").replace(":", "")
            filters.append(f"drawtext=text='{clean_txt}':fontfile={FONT}:fontsize={CFG['text_size']}:fontcolor=white:"
                           f"shadowcolor=black@0.8:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h-220:enable='between(t,{t_start},{t_end})'")
        f.write(",".join(filters))

    # 4. RENDU FINAL
    subprocess.run(f"ffmpeg -y -i base.mp4 -filter_script:v myscript.txt -c:v libx264 -crf 18 -c:a copy output.mp4", shell=True)
    print(f"✅ Vidéo IA terminée avec textes dynamiques Gemini !")

if __name__ == "__main__":
    start()
