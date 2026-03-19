"""
render.py — ViraCut Studio v14  ★ LesCrados.Ai Edition ★
═════════════════════════════════════════════════════════
v14.6 : UNIVERSAL JSON PARSER + AUTO-DOWNLOAD + GEQ SCANLINES
"""
import json, os, subprocess, sys, re, urllib.request

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "mode": "auto",
    "resolution": "720x1280",
    "fps": 24,
    "crf": 18,
}

def run(cmd):
    print(f"    $ {' '.join([str(c) for c in cmd[:15]])}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"STDERR: {r.stderr}")
        raise RuntimeError(f"FFmpeg failed (code {r.returncode})")
    return r

def download_file(url, dest):
    try:
        print(f"  ⬇️  Téléchargement : {dest}...")
        # User-agent pour éviter d'être bloqué par certains serveurs (Pexels/Giphy)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(dest, 'wb') as out_file:
            out_file.write(response.read())
        return True
    except Exception as e:
        print(f"  ❌ Erreur {url} : {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════
# LOGO & ENGINE
# ═══════════════════════════════════════════════════════════════════════

def build_logo_splash(output, opts):
    Wi, Hi = 720, 1280
    l1, l2 = opts.get("logo_l1", "VIRACUT").upper(), opts.get("logo_l2", "STUDIO").upper()
    l3, slogan = opts.get("logo_l3", "V14").upper(), opts.get("slogan", "AI GENERATED CONTENT").upper()

    bg = "color=c=black:s=720x1280:d=2.5[bg]"
    t_cf = f"drawtext=fontfile={FONT}:text='{l1}':fontcolor=white:fontsize=110:x=(w-tw)/2:y=480:alpha='if(lt(t,0.5),0,if(lt(t,1),(t-0.5)/0.5,1))'," \
           f"drawtext=fontfile={FONT}:text='{l2}':fontcolor=white:fontsize=110:x=(w-tw)/2:y=590:alpha='if(lt(t,0.7),0,if(lt(t,1.2),(t-0.7)/0.5,1))'," \
           f"drawtext=fontfile={FONT}:text='{l3}':fontcolor=white:fontsize=40:x=(w-tw)/2+240:y=610:alpha='if(lt(t,1),0,1)'," \
           f"drawbox=x=(w-200)/2:y=740:w=200:h=3:c=white@0.8:t=fill:enable='gt(t,1.2)'"
    
    # Scanline unique ultra-légère (GEQ)
    scan = "geq=lum='if(mod(Y,4),lum(X,Y),lum(X,Y)*0.75)'"
    
    vf = f"{bg};[bg]{t_cf},{scan},drawbox=y=0:h=129:c=black@0.5,drawbox=y=1151:h=129:c=black@0.5,format=yuv420p[v]"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "2.5", "-filter_complex", vf, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "18", output])

def build_cinema_segment(src, out, duration):
    vf = f"fps=24,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,eq=saturation=1.2:contrast=1.1,zoompan=z='min(zoom+0.001,1.3)':d={int(duration*24)}:s=720x1280"
    run(["ffmpeg", "-y", "-t", f"{duration:.3f}", "-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "18", out])

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    opts = DEFAULTS.copy()
    config_file = "p.json" if os.path.exists("p.json") else "result.json"
    
    if not os.path.exists(config_file):
        print(f"❌ Aucun JSON trouvé. Fichiers: {os.listdir('.')}")
        sys.exit(1)

    with open(config_file, "r") as f:
        data = json.load(f)
    
    # Extraction intelligente des segments (cherche 'segments' ou 'clips' ou la racine)
    segs = data.get("segments") or data.get("clips") or (data if isinstance(data, list) else [])
    opts.update(data.get("options", {}))

    if not segs:
        print(f"❌ Erreur: Structure JSON inconnue. Clés trouvées: {list(data.keys()) if isinstance(data, dict) else 'List'}")
        sys.exit(1)

    print(f"✅ {len(segs)} segments trouvés. Préparation...")

    processed = []
    for i, s in enumerate(segs):
        target = f"_raw_{i}.mp4"
        out = f"_cin_{i}.mp4"
        url = s.get("url") or s.get("src") or s.get("download_url")
        dur = s.get("duration") or 3.0
        
        # Téléchargement si URL, sinon utilisation locale
        if url and url.startswith("http"):
            download_file(url, target)
        
        if os.path.exists(target):
            print(f"🎬 Rendu {i+1}/{len(segs)} ({dur}s)...")
            build_cinema_segment(target, out, dur)
            processed.append(out)
        else:
            print(f"⚠️  Saut du segment {i} (fichier absent)")

    if not processed:
        print("❌ Aucun segment n'a pu être rendu.")
        sys.exit(1)

    # Assemblage
    with open("_lst.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    
    print("🔗 Assemblage final...")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_lst.txt", "-c", "copy", "_temp.mp4"])
    
    # Bandes noires + Logo
    run(["ffmpeg", "-y", "-i", "_temp.mp4", "-vf", "drawbox=y=0:h=65:c=black@1:t=fill,drawbox=y=1215:h=65:c=black@1:t=fill", "-c:v", "libx264", "-crf", "18", "_main.mp4"])
    
    build_logo_splash("_logo.mp4", opts)
    with open("_fin.txt", "w") as f: f.write("file '_main.mp4'\nfile '_logo.mp4'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_fin.txt", "-c", "copy", "output.mp4"])
    
    print("\n🚀 TERMINÉ : output.mp4 disponible.")

