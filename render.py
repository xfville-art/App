"""
render.py — ViraCut Studio v7
Version finale ultra-robuste
"""
import json, base64, os, subprocess, sys

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    print(f"Exec: {cmd[:100]}...")
    return subprocess.run(cmd, shell=True).returncode == 0

def start():
    if not os.path.exists("p.json"):
        print("Erreur: p.json introuvable")
        sys.exit(1)
        
    with open("p.json") as f:
        data = json.load(f)
    
    clips = data.get("videos", [])
    opts = data.get("options", {})
    W, H = opts.get("resolution", "720x1280").split("x")
    fps = opts.get("fps", 24)

    print(f"--- Debut du rendu ({len(clips)} clips) ---")

    # 1. Traitement des clips individuels
    seg_paths = []
    for i, v in enumerate(clips):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f:
            f.write(base64.b64decode(v["data"]))
        
        out = f"c{i}.mp4"
        # Scale + Pad + Zoom léger 1.04
        vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,zoompan=z='min(zoom+0.0005,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H},fps={fps}"
        run(f'ffmpeg -y -i {raw} -t 8 -vf "{vf}" -c:v libx264 -crf 18 -an {out}')
        seg_paths.append(out)

    # 2. Assemblage (Méthode simple)
    with open("list.txt", "w") as f:
        for p in seg_paths:
            f.write(f"file '{p}'\n")
    
    print("Assemblage final...")
    # On ajoute directement le filigrane ici pour être sûr
    mark = "drawtext=fontfile={}:text='LES CRADOS':fontsize=24:fontcolor=white@0.3:x=w-text_w-30:y=30".format(FONT)
    lb = "drawbox=y=0:h=80:c=black@1:t=fill,drawbox=y=ih-80:h=80:c=black@1:t=fill"
    
    # Création du fichier output.mp4 attendu par GitHub
    success = run(f'ffmpeg -y -f concat -safe 0 -i list.txt -vf "{lb},{mark}" -c:v libx264 -pix_fmt yuv420p output.mp4')

    if success and os.path.exists("output.mp4"):
        print("✅ SUCCÈS : output.mp4 créé")
    else:
        print("❌ ÉCHEC : Le fichier n'a pas pu être généré")

if __name__ == "__main__":
    start()
