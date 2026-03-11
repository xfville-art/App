"""
render.py — ViraCut Studio v7 ★ LesCrados.Ai Edition ★
═══════════════════════════════════════════════════════
FIX : Suppression totale des zooms pour éviter le débordement des textes
FIX : Mode "Fit-to-Screen" (Letterbox) pour garder tout le visuel visible
FIX : Correction des alertes FFmpeg
"""
import json, base64, os, subprocess, sys

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "resolution": "720x1280", 
    "fps": 24, 
    "crf": 18,
    "cinema_dur": 26, 
    "cinema_xfade": 0.5, # Transition plus courte pour plus de punch
    "cinema_kb_zoom": 1.0, # ZOOM DÉSACTIVÉ pour éviter de manger le texte
}

# ═══════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════
def cfg(opts, key):
    return opts.get(key, DEFAULTS.get(key))

def run(cmd):
    print(f"Running: {cmd[:100]}...")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print("Erreur FFmpeg détectée :", r.stderr[-500:])
    return r.stdout

def has_audio(path):
    cmd = f'ffprobe -v quiet -show_streams -select_streams a "{path}"'
    return len(run(cmd).strip()) > 0

# ═══════════════════════════════════════════════════════════════════════
# CONSTRUCTION DES SEGMENTS (SANS ZOOM)
# ═══════════════════════════════════════════════════════════════════════
def build_segment(src, seg_out, clip_dur, opts):
    W, H = cfg(opts, "resolution").split("x")
    fps = cfg(opts, "fps")
    
    # FILTRE : On ajuste à la largeur (720) et on centre verticalement (pad)
    # Cela garantit que le texte sur les bords de la vidéo originale ne sort jamais de l'écran.
    vf = (
        f"scale={W}:-1:flags=lanczos,"  # Redimensionne à 720px de large
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black," # Centre et ajoute du noir si besoin
        f"fps={fps}"
    )
    
    if has_audio(src):
        cmd = f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -vf "{vf}" -c:v libx264 -crf {cfg(opts,"crf")} -c:a aac -b:a 192k "{seg_out}"'
    else:
        # Ajout d'une piste audio vide si absente pour éviter les bugs de concaténation
        cmd = f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -f lavfi -i anullsrc=r=44100:cl=stereo -filter_complex "[0:v]{vf}[v]" -map "[v]" -map 1:a -c:v libx264 -crf {cfg(opts,"crf")} "{seg_out}"'
    
    run(cmd)

# ═══════════════════════════════════════════════════════════════════════
# ASSEMBLAGE FINAL
# ═══════════════════════════════════════════════════════════════════════
def assemble(seg_paths, opts):
    if not seg_paths: return
    
    # Création de la liste pour concaténation
    with open("list.txt", "w") as f:
        for p in seg_paths:
            f.write(f"file '{p}'\n")
    
    # Assemblage simple (plus stable que les filtres complexes pour éviter les alertes)
    cmd = f'ffmpeg -y -f concat -safe 0 -i list.txt -c copy output.mp4'
    run(cmd)

# ═══════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════════════
def start():
    if not os.path.exists("p.json"):
        print("Fichier p.json non trouvé.")
        sys.exit(1)
        
    with open("p.json") as f:
        data = json.load(f)
    
    clips = data.get("videos", [])
    opts = data.get("options", {})
    
    if not clips:
        print("Aucune vidéo dans p.json")
        return

    print(f"Traitement de {len(clips)} clips en mode PLEIN ÉCRAN SÉCURISÉ...")
    
    raw_paths = []
    for i, v in enumerate(clips):
        p = f"_raw_{i}.mp4"
        with open(p, "wb") as f:
            f.write(base64.b64decode(v["data"]))
        raw_paths.append(p)

    # Calcul de la durée par clip
    clip_dur = cfg(opts, "cinema_dur") / len(raw_paths)
    
    seg_paths = []
    for i, src in enumerate(raw_paths):
        out = f"_seg_{i}.mp4"
        build_segment(src, out, clip_dur, opts)
        seg_paths.append(out)

    assemble(seg_paths, opts)
    print("✓ Rendu terminé : output.mp4")

if __name__ == "__main__":
    start()
