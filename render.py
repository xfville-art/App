"""
render.py — ViraCut Studio v7  ★ LesCrados.Ai Edition ★
═══════════════════════════════════════════════════════
FIX : Gestion des fichiers temporaires pour éviter les erreurs "No such file"
ADD : Logo "LES CRADOS" discret haut-droite (30% opacité)
MODE : Cinéma Zoom 1.04 sans textes IA
"""
import json, base64, os, subprocess, sys

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "mode": "auto", "resolution": "720x1280", "fps": 24, "crf": 18,
    "cinema_dur": 26, "cinema_xfade": 0.8, 
    "cinema_kb_zoom": 1.04, "cinema_lb_h": 80,
}

def cfg(opts, key):
    return opts.get(key, DEFAULTS[key])

def run(cmd):
    print(f"    $ {cmd[:110]}...")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERR FFmpeg: {r.stderr[-500:]}")
        return False
    return True

def duration(path):
    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 0.0

# ═══════════════════════════════════════════════════════════════════════
# LOGO ANIME (OUTRO 5s)
# ═══════════════════════════════════════════════════════════════════════
def build_logo_splash(out, opts):
    W, H = cfg(opts, "resolution").split("x")
    fps, crf = cfg(opts, "fps"), cfg(opts, "crf")
    dur = 5.0
    vf = (
        f"drawtext=fontfile={FONT}:text='LES':fontsize=80:fontcolor=white:x=(w-text_w)/2:y=(h-300)/2:enable='gte(t,0.3)',"
        f"drawtext=fontfile={FONT}:text='CRADOS':fontsize=140:fontcolor=white:x=(w-text_w)/2:y=(h-100)/2:enable='gte(t,0.8)',"
        f"drawtext=fontfile={FONT}:text='.Ai':fontsize=80:fontcolor=#FF2442:x=(w-text_w)/2:y=(h+150)/2:enable='gte(t,1.7)',"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st=4.2:d=0.8"
    )
    run(f'ffmpeg -y -f lavfi -i "color=c=black:size={W}x{H}:rate={fps}" -f lavfi -i "anullsrc" -t {dur} -filter_complex "[0:v]{vf}[v]" -map "[v]" -map 1:a -c:v libx264 -pix_fmt yuv420p -crf {crf} "{out}"')

# ═══════════════════════════════════════════════════════════════════════
# COEUR DU RENDU
# ═══════════════════════════════════════════════════════════════════════
def start():
    if not os.path.exists("p.json"): sys.exit(1)
    with open("p.json") as f: data = json.load(f)
    clips_raw = data.get("videos", []); opts = data.get("options", {})
    W, H = cfg(opts, "resolution").split("x")
    
    print("--- ViraCut v7 : Rendu en cours ---")
    
    # 1. Export des vidéos
    raw_paths = []
    for i, v in enumerate(clips_raw):
        p = f"_r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v["data"]))
        raw_paths.append(p)

    # 2. Segments cinématiques
    n = len(raw_paths)
    clip_dur = (cfg(opts, "cinema_dur") - (cfg(opts, "cinema_xfade")*(n-1))) / n
    seg_paths = []
    for i, src in enumerate(raw_paths):
        out = f"_c{i}.mp4"
        kb = f"zoompan=z='min(zoom+0.0005,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}"
        vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,{kb},fps={cfg(opts,'fps')}"
        run(f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -vf "{vf}" -c:v libx264 -crf {cfg(opts,"crf")} -an "{out}"')
        seg_paths.append(out)

    # 3. Assemblage simple (Concatenation)
    with open("_list.txt", "w") as f:
        for p in seg_paths: f.write(f"file '{p}'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i _list.txt -c copy _assembled.mp4')

    # 4. Overlay final (Bandes noires + Filigrane discret)
    if os.path.exists("_assembled.mp4"):
        lb_h = cfg(opts, "cinema_lb_h")
        lb = f"drawbox=y=0:h={lb_h}:c=black@1:t=fill,drawbox=y=ih-{lb_h}:h={lb_h}:c=black@1:t=fill"
        mark = f"drawtext=fontfile={FONT}:text='LES CRADOS':fontsize=24:fontcolor=white@0.3:x=w-text_w-30:y=30"
        run(f'ffmpeg -y -i _assembled.mp4 -vf "{lb},{mark}" -c:v libx264 -crf {cfg(opts,"crf")} _main.mp4')
        
        # 5. Ajout Outro Logo
        build_logo_splash("_logo.mp4", opts)
        with open("_fin.txt", "w") as f:
            f.write("file '_main.mp4'\nfile '_logo.mp4'\n")
        run(f'ffmpeg -y -f concat -safe 0 -i _fin.txt -c:v libx264 -pix_fmt yuv420p output.mp4')
        print("✅ Terminé : output.mp4")
    else:
        print("❌ Erreur d'assemblage.")

if __name__ == "__main__":
    start()
