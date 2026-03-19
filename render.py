"""
render.py — ViraCut Studio v14  ★ LesCrados.Ai Edition ★
═════════════════════════════════════════════════════════
v14.5 : AUTO-DOWNLOAD MISSING RAWS + GEQ SCANLINES
"""
import json, base64, os, subprocess, sys, re, urllib.request, urllib.error

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "mode": "auto",
    "resolution": "720x1280",
    "fps": 24,
    "crf": 18,
    "audio_br": 192,
}

def run(cmd):
    print(f"    $ {' '.join([str(c) for c in cmd[:15]])}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"STDERR: {r.stderr}")
        raise RuntimeError(f"FFmpeg failed (code {r.returncode})")
    return r

def download_file(url, dest):
    """Télécharge un fichier avec gestion d'erreur basique."""
    try:
        print(f"  ⬇️ Téléchargement : {dest}...")
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        print(f"  ❌ Erreur téléchargement {url} : {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════
# LOGO SPLASH (OPTIMISÉ GEQ)
# ═══════════════════════════════════════════════════════════════════════

def build_logo_splash(output, opts):
    Wi, Hi = 720, 1280
    l1 = opts.get("logo_l1", "VIRACUT").upper()
    l2 = opts.get("logo_l2", "STUDIO").upper()
    l3 = opts.get("logo_l3", "V14").upper()
    slogan = opts.get("slogan", "AI GENERATED CONTENT").upper()

    bg_filter = "color=c=black:s=720x1280:d=2.5[bg]"
    dt_l1 = f"drawtext=fontfile={FONT}:text='{l1}':fontcolor=white:fontsize=110:x=(w-tw)/2:y=480:alpha='if(lt(t,0.5),0,if(lt(t,1), (t-0.5)/0.5, 1))'"
    dt_l2 = f"drawtext=fontfile={FONT}:text='{l2}':fontcolor=white:fontsize=110:x=(w-tw)/2:y=590:alpha='if(lt(t,0.7),0,if(lt(t,1.2), (t-0.7)/0.5, 1))'"
    dt_l3 = f"drawtext=fontfile={FONT}:text='{l3}':fontcolor=white:fontsize=40:x=(w-tw)/2+240:y=610:alpha='if(lt(t,1),0,1)'"
    dt_line = f"drawbox=x=(w-200)/2:y=740:w=200:h=3:color=white@0.8:t=fill:enable='gt(t,1.2)'"

    dt_slogan_parts = []
    for i, char in enumerate(slogan):
        delay = 1.4 + (i * 0.04)
        dt_slogan_parts.append(f"drawtext=fontfile={FONT}:text='{char}':fontcolor=white@0.7:fontsize=28:x=(w-300)/2 + {i*18}:y=780:enable='gt(t,{delay})'")

    scanline_filter = "geq=lum='if(mod(Y,4),lum(X,Y),lum(X,Y)*0.75)'"

    vignette_parts = [
        "drawbox=y=0:h=129:c=black@0.55:t=fill",
        f"drawbox=y={Hi-129}:h=129:c=black@0.55:t=fill",
        "drawbox=x=0:w=129:h=1280:c=black@0.40:t=fill",
        f"drawbox=x={Wi-129}:w=129:h=1280:c=black@0.40:t=fill"
    ]

    vf = (bg_filter + ";" + "[bg]" + ",".join([dt_l1, dt_l2, dt_l3, dt_line] + dt_slogan_parts + [scanline_filter] + vignette_parts) + ",format=yuv420p[v]")

    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:size=720x1280:rate=24", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "2.5", "-filter_complex", vf, "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", output]
    run(cmd)

def append_logo(video_in, opts):
    build_logo_splash("_logo.mp4", opts)
    with open("_concat_logo.txt", "w") as f:
        f.write(f"file '{video_in}'\nfile '_logo.mp4'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_concat_logo.txt", "-c", "copy", "output.mp4"])

# ═══════════════════════════════════════════════════════════════════════
# ENGINE
# ═══════════════════════════════════════════════════════════════════════

def build_cinema_segment(src, out, duration, opts):
    vf = f"fps=24,eq=saturation=1.18:brightness=-0.01:contrast=1.15,zoompan=z='min(zoom+0.0015,1.5)':d={int(duration*24)}:s=720x1280"
    run(["ffmpeg", "-y", "-t", f"{duration:.3f}", "-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "18", out])
    return out

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    opts = DEFAULTS.copy()
    config_file = "p.json" if os.path.exists("p.json") else "pa.json"
    
    if not os.path.exists(config_file):
        print("❌ Erreur: Aucun fichier de configuration (p.json) trouvé.")
        sys.exit(1)

    print(f"📂 Chargement de {config_file}...")
    with open(config_file, "r") as f:
        data = json.load(f)
        opts.update(data.get("options", {}))
        segments_data = data.get("segments", [])

    if not segments_data:
        print("❌ Erreur: Aucune donnée de segment dans le JSON.")
        sys.exit(1)

    # 1. TÉLÉCHARGEMENT AUTOMATIQUE
    raw_paths = []
    print(f"🎬 Préparation de {len(segments_data)} segments...")
    for i, seg in enumerate(segments_data):
        url = seg.get("url") or seg.get("src")
        target = f"_raw_{i}.mp4"
        
        if url:
            if download_file(url, target):
                raw_paths.append(target)
        elif os.path.exists(target):
            raw_paths.append(target)

    if not raw_paths:
        print("❌ Erreur: Impossible de récupérer les vidéos sources.")
        sys.exit(1)

    # 2. RENDU DES SEGMENTS
    processed = []
    for i, src in enumerate(raw_paths):
        out = f"_cin_{i}.mp4"
        dur = segments_data[i].get("duration", 3.0)
        print(f"  📽️ Rendu segment {i+1}/{len(raw_paths)} ({dur}s)...")
        build_cinema_segment(src, out, dur, opts)
        processed.append(out)

    # 3. ASSEMBLAGE
    with open("_concat.txt", "w") as f:
        for p in processed: f.write(f"file '{p}'\n")
    
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_concat.txt", "-c", "copy", "_assembled.mp4"])
    
    # 4. OVERLAY & LOGO
    run(["ffmpeg", "-y", "-i", "_assembled.mp4", "-vf", "drawbox=y=0:h=65:c=black@1:t=fill,drawbox=y=1215:h=65:c=black@1:t=fill", "-c:v", "libx264", "-crf", "18", "_premain.mp4"])
    append_logo("_premain.mp4", opts)
    
    print("\n✅ Rendu terminé : output.mp4")

