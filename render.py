import json, base64, os, subprocess, requests

CFG = {
    "res": "720x1280",
    "fps": 24,
    "base_size": 60,
    "api_key": os.getenv("GEMINI_API_KEY")
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={CFG['api_key']}"
    payload = {"contents": [{"parts": [{"text": f"Génère une punchline Crados (2 mots max) pour : {prompt}. Uniquement le texte."}]}]}
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.json()['candidates'][0]['content']['parts'][0]['text'].upper().replace("'", "").strip()
    except: return "GROS CRADO"

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

    # 3. SCRIPT DE FILTRES "HYPER-ANIMÉS"
    res = subprocess.run("ffprobe -v error -show_entries format=duration -of default=nokey=1 base.mp4", shell=True, capture_output=True, text=True)
    total_dur = float(res.stdout.strip())
    dur_seg = total_dur / len(processed)

    with open("myscript.txt", "w") as f:
        filters = []
        for i, txt in enumerate(dynamic_texts):
            t_start = i * dur_seg
            t_rel = f"(t-{t_start})"
            
            # --- ANIMATIONS COMPLEXES ---
            # 1. Effet Ressort (Elastic Pop) sur la taille
            # Le texte oscille rapidement avant de se stabiliser
            s_anim = f"{CFG['base_size']}*(1+0.5*exp(-5*{t_rel})*cos(2*PI*5*{t_rel}))"
            
            # 2. Rotation légère (Wobble)
            # On simule une rotation via un décalage de X sinusoïdal
            x_anim = f"(w-text_w)/2 + 10*sin(2*PI*{t_rel}/0.4)"
            
            # 3. Couleur Flashy (alternance Jaune / Vert Crado)
            color = f"if(lt(mod({t_rel},0.4),0.2),yellow,lime)"
            
            f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontcolor={color}:borderw=6:bordercolor=black:"
                     f"fontsize='{s_anim}':x='{x_anim}':y=(h-300):"
                     f"enable='between(t,{t_start},{t_start+dur_seg})'")
            filters.append(f_txt)
        
        f.write(",".join(filters))

    # 4. Rendu Final
    subprocess.run(f"ffmpeg -y -i base.mp4 -filter_script:v myscript.txt -c:v libx264 -crf 18 -c:a copy output.mp4", shell=True)
    print(f"🔥 Rendu v45 HYPER-ANIMÉ terminé.")

if __name__ == "__main__":
    start()
