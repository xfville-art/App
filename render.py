import json, base64, os, subprocess, requests, re

CFG = {
    "res": "720x1280",
    "fps": 24,
    "base_size": 75,
    "api_key": os.getenv("GEMINI_API_KEY")
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={CFG['api_key']}"
    payload = {"contents": [{"parts": [{"text": f"Génère un ou deux mots max style 'Les Crados' pour cette scène : {prompt}. Uniquement le texte, pas de ponctuation."}]}]}
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.json()['candidates'][0]['content']['parts'][0]['text'].upper().replace("'", "").strip()
    except: return "DEGUEULASSE"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    processed = []
    dynamic_texts = []

    # 1. Normalisation des clips
    for i, v in enumerate(videos):
        punchline = ask_gemini(v.get('prompt', 'monstre'))
        dynamic_texts.append(punchline)
        raw, out = f"r{i}.mp4", f"seg_{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']}"
        # On force l'audio pour éviter les erreurs de concat
        run(f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo -filter_complex "[0:v]{vf}[v];[0:a][1:a]amix=inputs=2:duration=first[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -shortest {out}')
        processed.append(out)

    # 2. Concaténation
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base.mp4")

    # 3. RÉCUPÉRATION DURÉE SÉCURISÉE (Plus de ValueError possible)
    # L'argument 'csv=p=0' ne renvoie QUE le chiffre
    res = run("ffprobe -v error -show_entries format=duration -of csv=p=0 base.mp4")
    try:
        total_dur = float(res.stdout.strip())
    except:
        total_dur = 15.0 # Fallback si vraiment ça échoue
    
    dur_seg = total_dur / len(processed)

    # 4. SCRIPT DE FILTRES AVEC ANIMATION KINÉTIQUE
    with open("myscript.txt", "w") as f:
        # Watermark
        filters = [f"drawtext=text='@LESCRADOS.AI':fontfile={FONT}:fontsize=22:fontcolor=white@0.3:x=w-text_w-40:y=60"]
        
        for i, txt in enumerate(dynamic_texts):
            t_start = i * dur_seg
            t_rel = f"(t-{t_start})"
            
            # ANIMATION : Pop-in élastique (le texte rebondit à l'arrivée)
            # Taille oscille puis se stabilise à 100%
            s_anim = f"{CFG['base_size']}*(1+0.6*exp(-4*{t_rel})*cos(2*PI*5*{t_rel}))"
            
            # POSITION : Léger tremblement continu (jitter)
            x_pos = f"((w-text_w)/2)+random(1)*5"
            y_pos = f"(h-300)+random(2)*5"
            
            f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontcolor=yellow:borderw=10:bordercolor=black:"
                     f"fontsize='{s_anim}':x='{x_pos}':y='{y_pos}':"
                     f"enable='between(t,{t_start},{t_start+dur_seg})'")
            filters.append(f_txt)
        
        f.write(",".join(filters))

    # 5. Rendu Final
    run(f"ffmpeg -y -i base.mp4 -filter_script:v myscript.txt -c:v libx264 -crf 17 -c:a copy output.mp4")
    print(f"✅ Rendu v47 terminé. Durée : {total_dur}s. Textes IA animés.")

if __name__ == "__main__":
    start()
