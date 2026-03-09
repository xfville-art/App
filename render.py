import json, base64, os, subprocess, urllib.request, time, re

# ─────────────────────────────────────────────────────────────────────
#  CONFIG VITALITÉ & RÉTENTION
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "total_target_dur": 25.0,
    "fps": 24,
    "res": "720:1280",
    "zoom_speed": 0.0012,
    "crf": 18
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction des Clips
    clips_raw = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"raw_{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips_raw.append(p)
    
    if not clips_raw: return
    num_clips = len(clips_raw)
    dur_per_clip = CFG["total_target_dur"] / num_clips

    # 2. Traitement Individuel (Zoom + Verticalité)
    # On prépare les segments vidéo propres avant d'ajouter le texte
    print(f"[1/2] Préparation de {num_clips} segments de {dur_per_clip:.1f}s...")
    segments = []
    vf_base = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"
    zoom = f"zoompan=z='min(zoom+{CFG['zoom_speed']},1.3)':d=1:s=720x1280:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    for i, cp in enumerate(clips_raw):
        out = f"seg_{i}.mp4"
        # On force la création d'une piste audio AAC pour chaque morceau
        run(f'ffmpeg -y -i {cp} -t {dur_per_clip} -vf "{vf_base},{zoom}" -c:v libx264 -c:a aac -ar 44100 -ac 2 {out}')
        if os.path.exists(out): segments.append(out)

    # 3. Assemblage final
    if not segments: return
    with open("list.txt", "w") as f:
        for s in segments: f.write(f"file '{s}'\n")

    # 4. AJOUT DES TEXTES DYNAMIQUES ET DES CTA (L'Intelligence de Rétention)
    print("[2/2] Assemblage final et injection des textes punchy...")
    
    # Biais cognitifs utilisés : Curiosité, Urgence, Engagement social
    texts = {
        "h1": "NE SWIPE PAS !",               # 0-3s : Stop-scroll (Urgence)
        "h2": "REGARDE CETTE CARTE...",       # 3-6s : Intrigue (Curiosité)
        "h3": "QUI S'EN SOUVIENT ?",          # 6-9s : Nostalgie (Engagement)
        "cta": "LACHE UN LIKE & COMMENTE !", # 15-20s : CTA Direct (Engagement social)
        "p": "ABONNE TOI POUR LA SUITE"       # 20-25s : Chute (Rétention)
    }

    # Style commun : Blanc, bordure noire épaisse pour la lisibilité
    draw_base = f"fontfile={FONT}:fontcolor=white:borderw=6:bordercolor=black"
    
    # Construction de la commande FFmpeg finale avec timings précis
    # Note comment les textes 'drawtext' s'activent ('enable') à des moments différents
    cmd_final = (
        f"ffmpeg -y -f concat -i list.txt -vf "
        f"\"drawtext=text='{texts['h1']}':{draw_base}:fontsize=90:x=(w-text_w)/2:y=200:enable='between(t,0,3)', "
        f"drawtext=text='{texts['h2']}':{draw_base}:fontsize=80:x=(w-text_w)/2:y=200:enable='between(t,3,6)', "
        f"drawtext=text='{texts['h3']}':{draw_base}:fontsize=70:fontcolor=yellow:x=(w-text_w)/2:y=200:enable='between(t,6,9)', "
        
        # Le CTA qui "débarque" au milieu de la vidéo pour booster l'algo
        f"drawtext=text='{texts['cta']}':{draw_base}:fontsize=65:fontcolor=yellow:x=(w-text_w)/2:y=h/2:enable='between(t,15,20)', "
        
        # La chute finale
        f"drawtext=text='{texts['p']}':{draw_base}:fontsize=60:x=(w-text_w)/2:y=h-300:enable='between(t,20,25)'\" "
        f"-c:v libx264 -crf 18 -c:a aac -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    if os.path.exists("output.mp4"): print("✅ output.mp4 généré avec textes dynamiques.")

if __name__ == "__main__":
    start()
