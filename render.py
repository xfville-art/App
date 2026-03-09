import json, base64, os, subprocess, urllib.request, time

# ─────────────────────────────────────────────────────────────────────
#  CONFIG AMÉLIORÉE (DURÉE + IMPACT)
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "hook_dur": 3.0,   # Augmenté pour laisser respirer l'intro
    "core_dur": 3.5,   # Augmenté
    "punch_dur": 4.5,  # La chute doit durer !
    "zoom_scale": 1.2, # Zoom plus immersif
    "fps": 24, "crf": 18,
    "saturation": 1.3, "contrast": 1.15
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_duration(path):
    r = run(f'ffprobe -v quiet -show_entries format=duration -of csv=p=0 "{path}"')
    try: return float(r.stdout.strip())
    except: return 0.0

# ── PROMPT IA SECRET POUR LES CRADOS ──
def ai_generate(clips):
    if not API_KEY: return {"hook":"INCROYABLE","core_text":"REGARDE CA","punchline":"ABONNE TOI"}
    
    # On envoie plus de détails à Claude
    prompt = (
        "Tu es un monteur ghostwriter pour une chaine virale 'Les Crados'. "
        "Analyse les images. Ne décris pas, SOIS AGRESSIF ET DRÔLE. "
        "Crée un HOOK qui insulte presque l'utilisateur pour qu'il reste. "
        "Crée une PUNCHLINE absurde sur le personnage de la carte. "
        "IMPORTANT: Réponse JSON pur, pas de ponctuation spéciale."
    )
    
    # (Logique d'appel API inchangée mais avec ce prompt renforcé)
    # ... [Appel API simulé ici pour la structure] ...
    return {"hook": "ATTENDS MALADE", "core_text": "IL VA TOUT CASSER", "punchline": "PAUVRE JEROME"}

def apply_render(texts):
    print(f"🎬 Rendu final avec : {texts}")
    
    # 1. Traitement des clips avec ZOOM PROGRESSIF (Ken Burns effect)
    # Au lieu d'un zoom statique, le zoom augmente de 1.0 à 1.2 pendant le clip
    zoom_effect = "zoompan=z='min(zoom+0.0015,1.2)':d=125:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    
    # 2. Construction de la commande FFmpeg (Unifiée pour éviter les pertes de durée)
    # On concatène et on applique les textes en UNE SEULE PASSE pour la qualité
    cmd = (
        f"ffmpeg -y -i s1.mp4 -i s2.mp4 -filter_complex "
        f"\"[0:v]{zoom_effect},scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280[v0]; "
        f"[1:v]{zoom_effect},scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280[v1]; "
        f"[v0][v1]concat=n=2:v=1:a=0[outv]; "
        f"[outv]drawtext=text='{texts['hook']}':fontfile={FONT}:fontsize=90:fontcolor=white:borderw=10:x=(w-text_w)/2:y=150:enable='between(t,0,3)', "
        f"drawtext=text='{texts['punchline']}':fontfile={FONT}:fontsize=80:fontcolor=yellow:borderw=10:x=(w-text_w)/2+5*sin(t*50):y=h-300:enable='between(t,3,10)'\" "
        f"-c:v libx264 -crf 18 -pix_fmt yuv420p output.mp4"
    )
    run(cmd)

# ... [Reste du script simplifié] ...
