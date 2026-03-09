import json, base64, os, subprocess, requests

CFG = {
    "res": "720x1280",
    "fps": 24,
    "base_size": 50,
    "api_key": os.getenv("GEMINI_API_KEY")
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={CFG['api_key']}"
    payload = {"contents": [{"parts": [{"text": f"Génère une punchline Crados (trash/drôle) de 2-3 mots max pour : {prompt}. Pas de ponctuation."}]}]}
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.json()['candidates'][0]['content']['parts'][0]['text'].upper().replace("'", "").strip()
    except: return "CATASTROPHE !"

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    processed = []
    dynamic_texts = []

    # 1. Préparation des segments
    for i, v in enumerate(videos):
        punchline = ask_gemini(v.get('prompt', 'monstre'))
        dynamic_texts.append(punchline)
        raw, out = f"r{i}.mp4", f"seg_{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']}"
        subprocess.run(f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo -filter_complex "[0:v]{vf}[v];[0:a][1:a]amix=inputs=2:duration=first[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -shortest {out}', shell=True)
        processed.append(out)

    # 2. Concaténation
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    subprocess.run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base.mp4", shell=True)

    # 3. SCRIPT DE FILTRES DYNAMIQUES (L'animation est ici)
    res = subprocess.run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 base.mp4", shell=True, capture_output=True, text=True)
    total_dur = float(res.stdout.strip())
    dur_seg = total_dur / len(processed)

    with open("myscript.txt", "w") as f:
        # Watermark fixe
        filters = [f"drawtext=text='@LESCRADOS':fontfile={FONT}:fontsize=20:fontcolor=white@0.2:x=w-text_w-40:y=60"]
        
        for i, txt in enumerate(dynamic_texts):
            t_start = i * dur_seg
            t_rel = f"(t-{t_start})" # Temps relatif au début du clip
            
            # --- FORMULES D'ANIMATION ---
            # Zoom "Pop" : Le texte part de 120% de sa taille et descend à 100% en 0.3s
            size = f"if(lt({t_rel},0.3), {CFG['base_size']}*(1.2-({t_rel}*0.66)), {CFG['base_size']})"
            
            # Flottement (Shake) : Oscillation légère en Y pour donner de la vie
            y_pos = f"(h-250)+(5*sin(2*PI*t/0.5))"
            
            f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontcolor=yellow:borderw=4:bordercolor=black:"
                     f"fontsize='{size}':x=(w-text_w)/2:y='{y_pos}':"
                     f"enable='between(t,{t_start},{t_start+dur_seg})'")
            filters.append(f_txt)
        
        f.write(",".join(filters))

    # 4. Rendu Final
    subprocess.run(f"ffmpeg -y -i base.mp4 -filter_script:v myscript.txt -c:v libx264 -crf 18 -c:a copy output.mp4", shell=True)

if __name__ == "__main__":
    start()
