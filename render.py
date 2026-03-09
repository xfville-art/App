import json, base64, os, subprocess, requests

CFG = {
    "res": "720x1280",
    "fps": 24,
    "base_size": 70,
    "api_key": os.getenv("GEMINI_API_KEY")
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={CFG['api_key']}"
    payload = {"contents": [{"parts": [{"text": f"Donne 1 mot crado pour : {prompt}. Pas de ponctuation."}]}]}
    try:
        r = requests.post(url, json=payload, timeout=8)
        # On nettoie tout caractère spécial pour FFmpeg
        txt = r.json()['candidates'][0]['content']['parts'][0]['text']
        return "".join(e for e in txt if e.isalnum()).upper()
    except: return "HORREUR"

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    processed = []
    dynamic_texts = []

    # 1. Normalisation sans compromis
    for i, v in enumerate(videos):
        punchline = ask_gemini(v.get('prompt', 'monstre'))
        dynamic_texts.append(punchline)
        raw, out = f"r{i}.mp4", f"seg_{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps={CFG['fps']}"
        # On crée un segment parfait avec audio
        cmd = f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo -filter_complex "[0:v]{vf}[v];[0:a][1:a]amix=inputs=2:duration=first[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 20 -preset ultrafast -shortest {out}'
        subprocess.run(cmd, shell=True, check=True)
        processed.append(out)

    # 2. Concaténation
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    subprocess.run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base.mp4", shell=True, check=True)

    # 3. Création du script de filtres (Version ultra-stable)
    # On utilise 3.0s par clip car c'est la norme de tes générations
    dur_seg = 3.0
    
    with open("myscript.txt", "w", encoding="utf-8") as f:
        # Watermark de base
        filters = [f"drawtext=text='LES CRADOS':fontfile={FONT}:fontsize=24:fontcolor=white@0.3:x=w-text_w-40:y=60"]
        
        for i, txt in enumerate(dynamic_texts):
            t_start = i * dur_seg
            t_end = (i + 1) * dur_seg
            t_rel = f"(t-{t_start})"
            
            # ANIMATION : Le texte "respire" (zoom sinusoïdal permanent)
            # Pas d'exponentielle complexe pour éviter les erreurs de calcul
            s_anim = f"{CFG['base_size']}*(1+0.1*sin(2*PI*{t_rel}))"
            
            # On construit la ligne sans aucun guillemet interne superflu
            f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontcolor=yellow:borderw=10:bordercolor=black:"
                     f"fontsize={s_anim}:x=(w-text_w)/2:y=(h-350):enable='between(t,{t_start},{t_end})'")
            filters.append(f_txt)
        
        # On joint tout par des virgules sans espaces
        f.write(",".join(filters))

    # 4. Rendu Final avec vérification
    print("Démarrage du mixage final...")
    final_cmd = "ffmpeg -y -i base.mp4 -filter_script:v myscript.txt -c:v libx264 -crf 18 -preset fast -c:a copy output.mp4"
    subprocess.run(final_cmd, shell=True, check=True)
    print("Fichier output.mp4 généré avec succès.")

if __name__ == "__main__":
    start()
