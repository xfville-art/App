"""
render.py — ViraCut Studio v14  ★ LesCrados.Ai Edition ★
═════════════════════════════════════════════════════════
v14.9 : BASE64 OK + SECURE CONCAT (RE-ENCODE) + GEQ SCANLINES
"""
import json, os, subprocess, sys, re, urllib.request, base64

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
        # Affiche plus de détails sur l'erreur FFmpeg pour le debug
        print(f"❌ FFmpeg Error (Code {r.returncode})")
        print(f"STDERR: {r.stderr[-1000:]}") 
        raise RuntimeError(f"FFmpeg failed")
    return r

def handle_source(data_str, dest):
    if not data_str: return False
    
    # BASE64 (Data URI ou brut)
    if "base64," in str(data_str) or len(str(data_str)) > 5000:
        try:
            print(f"  📦 Décodage Base64 vers {dest}...")
            b64_data = str(data_str).split("base64,")[-1]
            with open(dest, "wb") as f:
                f.write(base64.b64decode(b64_data))
            return True
        except Exception as e:
            print(f"  ❌ Erreur décodage Base64 : {e}")
            return False

    # URL HTTP
    if str(data_str).startswith("http"):
        try:
            print(f"  ⬇️  Téléchargement : {data_str[:50]}...")
            req = urllib.request.Request(data_str, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response, open(dest, 'wb') as out_file:
                out_file.write(response.read())
            return True
        except Exception as e:
            print(f"  ❌ Erreur URL : {e}")
            return False
    return False

# ═══════════════════════════════════════════════════════════════════════
# LOGO & ENGINE
# ═══════════════════════════════════════════════════════════════════════

def build_logo_splash(output, opts):
    l1, l2 = opts.get("logo_l1", "VIRACUT").upper(), opts.get("logo_l2", "STUDIO").upper()
    l3, slogan = opts.get("logo_l3", "V14").upper(), opts.get("slogan", "AI GENERATED CONTENT").upper()

    bg = "color=c=black:s=720x1280:d=2.5[bg]"
    t_cf = f"drawtext=fontfile={FONT}:text='{l1}':fontcolor=white:fontsize=110:x=(w-tw)/2:y=480:alpha='if(lt(t,0.5),0,if(lt(t,1),(t-0.5)/0.5,1))'," \
           f"drawtext=fontfile={FONT}:text='{l2}':fontcolor=white:fontsize=110:x=(w-tw)/2:y=590:alpha='if(lt(t,0.7),0,if(lt(t,1.2),(t-0.7)/0.5,1))'," \
           f"drawtext=fontfile={FONT}:text='{l3}':fontcolor=white:fontsize=40:x=(w-tw)/2+240:y=610:alpha='if(lt(t,1),0,1)'," \
           f"drawbox=x=(w-200)/2:y=740:w=200:h=3:c=white@0.8:t=fill:enable='gt(t,1.2)'"
    
    scan = "geq=lum='if(mod(Y,4),lum(X,Y),lum(X,Y)*0.75)'"
    vf = f"{bg};[bg]{t_cf},{scan},drawbox=y=0:h=129:c=black@0.5,drawbox=y=1151:h=129:c=black@0.5,format=yuv420p[v]"
    # On ajoute une piste audio silencieuse pour éviter les soucis de concat
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "2.5", "-filter_complex", vf, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", output])

def build_cinema_segment(src, out, duration):
    # On force l'audio à 2 canaux même si absent de la source
    vf = f"fps=24,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,eq=saturation=1.2:contrast=1.1,zoompan=z='min(zoom+0.001,1.3)':d={int(duration*24)}:s=720x1280"
    run(["ffmpeg", "-y", "-t", f"{duration:.3f}", "-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-af", "aresample=async=1", out])

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    opts = DEFAULTS.copy()
    config_file = "p.json" if os.path.exists("p.json") else "pa.json"
    
    if not os.path.exists(config_file):
        print("❌ Aucun JSON trouvé.")
        sys.exit(1)

    with open(config_file, "r") as f:
        data = json.load(f)
    
    segs = data.get("videos") or data.get("segments") or data.get("clips") or []
    opts.update(data.get("options", {}))

    print(f"✅ {len(segs)} segments identifiés. Décodage et Rendu...")

    processed = []
    for i, s in enumerate(segs):
        target, out = f"_raw_{i}.mp4", f"_cin_{i}.mp4"
        src_data = s.get("url") or s.get("src") or s.get("data")
        dur = s.get("duration") or 3.0
        
        if handle_source(src_data, target):
            print(f"🎬 Rendu segment {i+1}/{len(segs)}...")
            try:
                build_cinema_segment(target, out, dur)
                processed.append(out)
            except Exception as e:
                print(f"⚠️  Erreur segment {i}: {e}")

    if not processed:
        print("❌ Échec : aucun segment produit.")
        sys.exit(1)

    # ASSEMBLAGE FINAL (Mode Robuste : Complex Filter Concat)
    # Le mode concat file (copy) échoue souvent avec des fichiers d'origines diverses.
    # On utilise filter_complex concat pour tout uniformiser.
    print("🔗 Assemblage des segments (re-encodage sécurisé)...")
    inputs = []
    for p in processed:
        inputs.extend(["-i", p])
    
    filter_concat = "".join([f"[{i}:v][{i}:a]" for i in range(len(processed))])
    filter_concat += f"concat=n={len(processed)}:v=1:a=1[v][a]"
    
    run(["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_concat, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "_temp.mp4"])
    
    # Overlays + Logo
    run(["ffmpeg", "-y", "-i", "_temp.mp4", "-vf", "drawbox=y=0:h=65:c=black@1:t=fill,drawbox=y=1215:h=65:c=black@1:t=fill", "-c:v", "libx264", "-crf", "18", "_main.mp4"])
    
    build_logo_splash("_logo.mp4", opts)
    
    # Concaténation finale Main + Logo (re-encodage pour être sûr)
    run(["ffmpeg", "-y", "-i", "_main.mp4", "-i", "_logo.mp4", "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "output.mp4"])
    
    print("\n🚀 RENDU RÉUSSI : output.mp4 généré.")

