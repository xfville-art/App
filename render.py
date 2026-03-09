import json, base64, os, subprocess, requests, re

CFG = {
    "res": "720x1280",
    "fps": 24,
    "base_size": 70,
    "api_key": os.getenv("GEMINI_API_KEY")
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={CFG['api_key']}"
    payload = {"contents": [{"parts": [{"text": f"Génère un mot ou deux max (style trash/crado) pour : {prompt}. Pas de ponctuation."}]}]}
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.json()['candidates'][0]['content']['parts'][0]['text'].upper().replace("'", "").strip()
    except: return "MUTATION"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

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
        run(f'ffmpeg -y -i {raw} -f lavfi -i anullsrc=r=44100:cl=stereo -filter_complex "[0:v]{vf}[v];[0:a][1:a]amix=inputs=2:duration=first[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -shortest {out}')
        processed.append(out)

    # 2. Concaténation
    with open("list.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    run("ffmpeg -y -f concat -safe 0 -i list.txt -c copy base.mp4")

    # 3. RÉCUPÉRATION DURÉE (Correction du bug Log 1000026826)
    res = run("ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 base.mp4")
    # On utilise un regex pour extraire uniquement le nombre, au cas où ffprobe bave
    duration_match = re.search(r"(\d+\.\d+)", res.stdout)
    total_dur = float(duration_match.group(1)) if duration_match else 15.0
    dur_seg = total_dur / len(processed)

    # 4. SCRIPT DE FILTRES "ULTRA-ANIMÉS"
    with open("myscript.txt", "w") as f:
        filters = [f"drawtext=text='@LESCRADOS':fontfile={FONT}:fontsize=20:fontcolor=white@0.2:x=w-text_w-40:y=60"]
        
        for i, txt in enumerate(dynamic_texts):
            t_start = i * dur_seg
            t_rel = f"(t-{t_start})"
            
            # --- ANIMATIONS AGRESSIVES ---
            # POP & SHAKE : Le texte arrive avec un zoom énorme et vibre
            s_anim = f"{CFG['base_size']}*(1+0.8*exp(-4*{t_rel})*abs(cos(2*PI*10*{t_rel})))"
            
            # POSITION : Tremblement aléatoire (Jitter)
            x_jitter = f"((w-text_w)/2)+random(1)*10"
            y_jitter = f"(h-350)+random(2)*10"
            
            # COULEUR : Flash entre Blanc et Jaune Toxique
            color = f"if(lt(mod({t_rel},0.2),0.1),white,0x00FFFF)"
            
            f_txt = (f"drawtext=text='{txt}':fontfile={FONT}:fontcolor={color}:borderw=8:bordercolor=black:"
                     f"fontsize='{s_anim}':x='{x_jitter}':y='{y_jitter}':"
                     f"enable='between(t,{t_start},{t_start+dur_seg})'")
            filters.append(f_txt)
        
        f.write(",".join(filters))

    # 5. Rendu Final
    run(f"ffmpeg -y -i base.mp4 -filter_script:v myscript.txt -c:v libx264 -crf 16 -c:a copy output.mp4")
    print(f"✅ Master v46 KINETIC terminé - Durée: {total_dur}s")

if __name__ == "__main__":
    start()
