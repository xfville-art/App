import json, base64, os, subprocess, urllib.request, time

# ─────────────────────────────────────────────────────────────────────
#  CONFIG BOOSTÉE (DURÉE + COMPATIBILITÉ)
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "hook_dur": 3.5,    # Intro plus longue pour la rétention
    "punch_dur": 4.5,   # Fin plus longue pour l'engagement
    "zoom_scale": 1.15, 
    "fps": 24, 
    "crf": 18,
    "saturation": 1.25, 
    "contrast": 1.1
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def run(cmd):
    print(f"  ▸ {cmd[:100]}...")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_duration(path):
    r = run(f'ffprobe -v quiet -show_entries format=duration -of csv=p=0 "{path}"')
    try: return float(r.stdout.strip())
    except: return 0.0

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction et Sauvegarde des clips
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        path = f"raw_{i}.mp4"
        with open(path, "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        clips.append(path)
    
    if len(clips) < 2: 
        print("❌ Pas assez de clips"); return

    # 2. IA Vision / Textes (Fallback si erreur)
    texts = {"hook": "REGARDE BIEN CA", "punch": "ABONNE TOI"}
    # ... (Ton code d'appel API ici si nécessaire)

    # 3. Préparation des segments (Normalisation)
    # On s'assure que chaque segment fait AU MOINS la durée demandée
    seg_hook = "seg_hook.mp4"
    seg_punch = "seg_punch.mp4"
    
    # Crop & Scale en une étape pour éviter les déformations
    vf_base = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"
    
    run(f'ffmpeg -y -i {clips[0]} -t {CFG["hook_dur"]} -vf "{vf_base}" -c:v libx264 -an {seg_hook}')
    run(f'ffmpeg -y -i {clips[-1]} -t {CFG["punch_dur"]} -vf "{vf_base}" -c:v libx264 -an {seg_punch}')

    # 4. Montage Final avec Effets (Zoom Progressif + Textes)
    # Utilisation de filter_complex pour garantir la création de output.mp4
    zoom = "zoompan=z='min(zoom+0.0015,1.2)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    
    cmd_final = (
        f"ffmpeg -y -i {seg_hook} -i {seg_punch} -filter_complex "
        f"\"[0:v]{zoom}[v0]; [1:v]{zoom}[v1]; [v0][v1]concat=n=2:v=1:a=0[cv]; "
        f"[cv]drawtext=text='{texts['hook']}':fontfile={FONT}:fontsize=80:fontcolor=white:borderw=5:x=(w-text_w)/2:y=200:enable='between(t,0,3)', "
        f"drawtext=text='{texts['punch']}':fontfile={FONT}:fontsize=70:fontcolor=yellow:borderw=5:x=(w-text_w)/2:y=h-300:enable='between(t,3,10)', "
        f"eq=saturation={CFG['saturation']}:contrast={CFG['contrast']}\" "
        f"-c:v libx264 -crf {CFG['crf']} -pix_fmt yuv420p output.mp4"
    )
    
    res = run(cmd_final)
    if os.path.exists("output.mp4"):
        print("✅ output.mp4 généré avec succès !")
    else:
        print(f"❌ Erreur FFmpeg : {res.stderr}")

if __name__ == "__main__":
    start()
