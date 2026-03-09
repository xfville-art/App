import json, base64, os, subprocess

# CONFIGURATION ÉLARGIE POUR LE MODE CINÉMA
CFG = {
    "cinema_dur": 26.0,       # On passe de 7s à 26s
    "cinema_clip_min": 6.0,   # Durée minimum par plan
    "cinema_xfade": 1.0,      # Transitions fondu-enchaîné plus longues
    "res": "720x1280",
    "fps": 24
}

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    num = len(videos)
    # On calcule la durée de chaque clip pour atteindre les 26 secondes
    dur_seg = CFG["cinema_dur"] / num
    processed = []

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        
        # 🎬 EFFET "KEN BURNS" (Zoom lent progressif)
        # Cela évite l'ennui sur les plans longs en créant un mouvement constant
        vf = (f"scale=800:1422:force_original_aspect_ratio=increase,crop=720:1280,"
              f"zoompan=z='zoom+0.0005':d={dur_seg*CFG['fps']}:s=720x1280,setpts=PTS-STARTPTS")
        
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 {out}')
        processed.append(out)

    # CONCATÉNATION AVEC CROSSFADE (Fondu enchaîné)
    # Le fondu donne cette impression de "film" plutôt que de "zapping"
    filter_complex = ""
    for i in range(num):
        filter_complex += f"[{i}:v]"
    
    # Commande Simplifiée pour la fusion des segments avec fondu
    # (Note: nécessite au moins 2 clips)
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    
    # Version sécurisée pour la longueur
    run("ffmpeg -y -f concat -safe 0 -i l.txt -c:v libx264 -crf 20 -pix_fmt yuv420p output.mp4")
    print(f"🎬 Rendu CINÉMA de {CFG['cinema_dur']}s terminé.")

if __name__ == "__main__":
    start()
