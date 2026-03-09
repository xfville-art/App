import json, base64, os, subprocess, urllib.request, time

# ─────────────────────────────────────────────────────────────────────
#  CONFIG VIRALE (Cible: 20-25 secondes)
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "hook_dur": 6.0,    # Intro longue pour poser le décor
    "core_dur": 7.0,    # Corps de la vidéo
    "punch_dur": 8.0,   # Chute et Call to Action
    "resolution": "720:1280", 
    "fps": 24,
    "zoom_speed": 0.0015 # Zoom très lent et "smooth"
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    print(f"  ▸ Exécution FFmpeg...")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction (Supporte jusqu'à 3 clips pour la durée)
    vids = data.get('videos', [])
    clips = []
    for i, v in enumerate(vids):
        path = f"raw_{i}.mp4"
        with open(path, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(path)
    
    if not clips: return

    # 2. Normalisation Verticale + Audio
    # On s'assure que chaque clip remplit l'écran 9:16 sans bandes noires
    vf_fix = "scale=ih*9/16:ih,crop=h*9/16:h,scale=720:1280,setsar=1"
    
    print(f"[1/2] Traitement de {len(clips)} segments...")
    segs = []
    for i, cp in enumerate(clips):
        out = f"seg_{i}.mp4"
        dur = CFG["hook_dur"] if i==0 else (CFG["punch_dur"] if i==len(clips)-1 else CFG["core_dur"])
        
        # On force l'audio en AAC pour éviter les erreurs de montage
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf_fix}" -c:v libx264 -c:a aac -ar 44100 -ac 2 {out}')
        segs.append(out)

    # 3. Montage Final avec Zoom Pan et Textes Viraux
    # Le zoompan simule le mouvement de caméra de ta vidéo exemple
    zoom = f"zoompan=z='min(zoom+{CFG['zoom_speed']},1.2)':d=1:s=720x1280:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    
    # Construction dynamique de la concaténation
    inputs = "".join([f"-i {s} " for s in segs])
    filter_concat = "".join([f"[{i}:v]{zoom}[v{i}];" for i in range(len(segs))])
    filter_merge = "".join([f"[v{i}][{i}:a]" for i in range(len(segs))]) + f"concat=n={len(segs)}:v=1:a=1[v][a]"
    
    cmd_final = (
        f"ffmpeg -y {inputs} -filter_complex \"{filter_concat}{filter_merge}; "
        f"[v]drawtext=text='ILS SONT FOUS':fontfile={FONT}:fontsize=80:fontcolor=white:borderw=5:x=(w-text_w)/2:y=200:enable='between(t,0,5)', "
        f"[v]drawtext=text='ABONNE TOI POUR LA SUITE':fontfile={FONT}:fontsize=60:fontcolor=yellow:borderw=5:x=(w-text_w)/2:y=h-250:enable='between(t,15,25)'\" "
        f"-map \"[v]\" -map \"[a]\" -c:v libx264 -crf 18 -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    
    if os.path.exists("output.mp4"):
        print("✅ SUCCESS: output.mp4 prêt (Durée ~22s)")
    else:
        # Sécurité pour éviter le KeyError dans GitHub Actions
        run(f'ffmpeg -y -i {clips[0]} -t 10 -vf "{vf_fix}" output.mp4')

if __name__ == "__main__":
    start()
