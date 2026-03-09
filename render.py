import json, base64, os, subprocess, urllib.request, time, re

# ─────────────────────────────────────────────────────────────────────
#  CONFIG VITALITÉ & SÉCURITÉ
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "total_target_dur": 25.0,
    "fps": 24,
    "res": "720:1280",
    "zoom_speed": 0.0012, # Zoom constant ultra-fluide
    "crf": 18
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

# ── FONCTION DE PROTECTION (Le "Bouclier") ──
def clean_text(t):
    if not t: return ""
    # 1. Supprime les deux-points (:) et les guillemets (") et (')
    # 2. Remplace les caractères spéciaux par des espaces ou rien
    t = t.replace(":", " ").replace('"', " ").replace("'", " ")
    # 3. Supprime tout ce qui n'est pas alphanumérique ou ponctuation de base
    t = re.sub(r"[^a-zA-Z0-9 !?À-ÿ]", "", t)
    return t.strip().upper() # Force en Majuscules pour le style viral

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction
    clips_raw = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"raw_{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips_raw.append(p)
    
    if not clips_raw: return
    num_clips = len(clips_raw)
    dur_per_clip = CFG["total_target_dur"] / num_clips

    # 2. IA Vision (Avec consignes de sécurité strictes)
    texts = {"h": "ILS SONT COMPLÈTEMENT CRADOS", "p": "ABONNE TOI POUR LA SUITE"}
    
    if API_KEY:
        # Prompt modifié pour interdire les caractères spéciaux à la source
        prompt = "Génère un hook et une punchline pour Les Crados. INTERDICTION de mettre des guillemets ou des deux-points. Réponds en JSON : {\"hook\": \"...\", \"punch\": \"...\"}"
        # ... (Logique d'appel API Claude ici) ...

    # Nettoyage de sécurité final (Même si l'IA se trompe)
    safe_h = clean_text(texts.get("h", "ATTENTION"))
    safe_p = clean_text(texts.get("p", "SUITE BIENTÔT"))

    # 3. Traitement des segments (Verticalité + Zoom)
    segments = []
    vf_base = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"
    zoom = f"zoompan=z='min(zoom+{CFG['zoom_speed']},1.3)':d=1:s=720x1280:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    for i, cp in enumerate(clips_raw):
        out = f"seg_{i}.mp4"
        # On force la création d'une piste audio AAC pour chaque morceau
        run(f'ffmpeg -y -i {cp} -t {dur_per_clip} -vf "{vf_base},{zoom}" -c:v libx264 -c:a aac -ar 44100 -ac 2 {out}')
        if os.path.exists(out): segments.append(out)

    # 4. Assemblage final
    if not segments: return
    with open("list.txt", "w") as f:
        for s in segments: f.write(f"file '{s}'\n")

    # On utilise des simples quotes (') pour FFmpeg et on a déjà purgé les (') du texte
    cmd_final = (
        f"ffmpeg -y -f concat -i list.txt -vf "
        f"\"drawtext=text='{safe_h}':fontfile={FONT}:fontsize=75:fontcolor=white:borderw=6:bordercolor=black:x=(w-text_w)/2:y=250:enable='between(t,0,6)', "
        f"drawtext=text='{safe_p}':fontfile={FONT}:fontsize=60:fontcolor=yellow:borderw=6:bordercolor=black:x=(w-text_w)/2:y=h-300:enable='between(t,{CFG['total_target_dur']-6},{CFG['total_target_dur']})'\" "
        f"-c:v libx264 -crf {CFG['crf']} -c:a aac -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    if os.path.exists("output.mp4"): print("✅ output.mp4 généré et protégé.")

if __name__ == "__main__":
    start()
