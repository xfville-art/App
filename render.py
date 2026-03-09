import json, base64, os, subprocess, requests

CFG = {
    "res": "720x1280",
    "fps": 24,
    "base_size": 75,
    "api_key": os.getenv("GEMINI_API_KEY")
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={CFG['api_key']}"
    payload = {"contents": [{"parts": [{"text": f"Génère un ou deux mots max style 'Les Crados' pour cette scène : {prompt}. Uniquement le texte."}]}]}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json()['candidates'][0]['content']['parts'][0]['text'].upper().replace("'", "").strip()
    except: return "DEGUEULASSE"

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    processed = []
    dynamic_texts = []

    # 1. Normalisation stricte
    for i, v in enumerate(videos):
        punchline = ask_gemini(v.get('prompt', 'monstre'))
        dynamic_texts.append(punchline)
        raw, out = f"r{i}.mp4", f"seg_{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        # On simplifie le filtre au maximum pour éviter les plantages
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']}"
        cmd = f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo -filter_complex "[0:v]{vf}[v];[0:a][1:a]amix=inputs=2:duration=first[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 23 -preset ultrafast -shortest {out}'
        subprocess.run(cmd, shell=True, check=True) # check=True force l'arrêt si FFmpeg échoue
        processed.append(out)

    # 2. Concaténation ultra-simple
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    subprocess.run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base.mp4", shell=True, check=True)

    # 3. Calcul de la durée sans ffprobe (Basé sur le nombre de clips)
    # Souvent ffprobe échoue dans l'environnement GitHub, on va estimer la durée
    dur_seg = 3.0 # On part sur 3s par clip par défaut pour l'animation
    total_dur = len(processed) * dur_seg

    # 4. Script de filtres
    with open("myscript.txt", "w") as f:
        filters = [f"drawtext=text='@LESCRADOS.AI':fontfile={FONT}:fontsize=22:fontcolor=white@0.3:x=w-text_w-40:y=60"]
        for i, txt in enumerate(dynamic_texts):
            t_start, t_end = i * dur_seg, (i+1) * dur_seg
            t_rel = f"(t-{t_start})"
            # Animation Pop-in plus robuste
            s_anim = f"{CFG['base_size']}*(1+0.5*exp(-3*{t_rel})*cos(2*PI*4*{t_rel}))"
            f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontcolor=yellow:borderw=10:bordercolor=black:"
                     f"fontsize='{s_anim}':x=(w-text_w)/2:y=(h-300):enable='between(t,{t_start},{t_end})'")
            filters.append(f_txt)
        f.write(",".join(filters))

    # 5. Rendu Final avec logs complets
    final_cmd = "ffmpeg -y -i base.mp4 -filter_script:v myscript.txt -c:v libx264 -crf 20 -preset fast -c:a copy output.mp4"
    print(f"Lancement du rendu final...")
    subprocess.run(final_cmd, shell=True, check=True)

if __name__ == "__main__":
    start()
