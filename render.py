"""
render.py — ViraCut Studio v14  ★ LesCrados.Ai Edition ★
═════════════════════════════════════════════════════════
v14.2 : FIX CRITICAL - SCANLINE OPTIMIZATION + AUTO-DETECT RESTORED
"""
import json, base64, os, subprocess, sys, re, urllib.request, urllib.error

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "mode":            "auto",
    "resolution":      "720x1280",
    "fps":             24,
    "crf":             18,
    "audio_br":        192,
    "fade_dur":        0.3,
    "cinema_dur":      12,
    "cinema_clip_min": 7,
    "cinema_clip_max": 12,
}

def run(cmd):
    # Print d'aide au debug
    print(f"    $ {' '.join([str(c) for c in cmd[:15]])}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"STDERR: {r.stderr}")
        raise RuntimeError(f"FFmpeg failed (code {r.returncode})")
    return r

# ═══════════════════════════════════════════════════════════════════════
# LOGO SPLASH (LA FONCTION OPTIMISÉE)
# ═══════════════════════════════════════════════════════════════════════

def build_logo_splash(output, opts):
    """Génère l'intro/outro avec logo et effet CRT optimisé via filtre GEQ."""
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

    # --- FIX SCANLINES : Utilisation de GEQ au lieu de 300+ drawbox ---
    scanline_filter = "geq=lum='if(mod(Y,4),lum(X,Y),lum(X,Y)*0.75)'"

    vignette_parts = [
        "drawbox=y=0:h=129:c=black@0.55:t=fill",
        f"drawbox=y={Hi-129}:h=129:c=black@0.55:t=fill",
        "drawbox=x=0:w=129:h=1280:c=black@0.40:t=fill",
        f"drawbox=x={Wi-129}:w=129:h=1280:c=black@0.40:t=fill"
    ]

    vf = (
        bg_filter + ";" +
        "[bg]" + ",".join([dt_l1, dt_l2, dt_l3, dt_line] + dt_slogan_parts + [scanline_filter] + vignette_parts) +
        ",format=yuv420p[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:size=720x1280:rate=24",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "2.5",
        "-filter_complex", vf,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
        output
    ]
    run(cmd)

def append_logo(video_in, opts):
    build_logo_splash("_logo.mp4", opts)
    with open("_concat_logo.txt", "w") as f:
        f.write(f"file '{video_in}'\n")
        f.write("file '_logo.mp4'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_concat_logo.txt", "-c", "copy", "output.mp4"]
    run(cmd)

# ═══════════════════════════════════════════════════════════════════════
# ENGINE
# ═══════════════════════════════════════════════════════════════════════

def build_cinema_segment(src, out, duration, zoom_speed, opts, role="core"):
    # On reprend les paramètres visuels d'origine (saturation, contrast)
    vf = f"fps=24,eq=saturation=1.18:brightness=-0.01:contrast=1.15,zoompan=z='min(zoom+0.0015,1.5)':d={int(duration*24)}:s=720x1280"
    cmd = ["ffmpeg", "-y", "-t", f"{duration:.3f}", "-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "18", out]
    run(cmd)
    return out

def assemble_cinema(segments, opts):
    with open("_concat.txt", "w") as f:
        for s in segments:
            f.write(f"file '{s}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_concat.txt", "-c", "copy", "_assembled.mp4"]
    run(cmd)

def build_cinema_overlay_no_text(opts):
    # Bandes noires cinéma
    cmd = [
        "ffmpeg", "-y", "-i", "_assembled.mp4",
        "-vf", "drawbox=y=0:h=65:c=black@1:t=fill,drawbox=y=1215:h=65:c=black@1:t=fill",
        "-c:v", "libx264", "-crf", "18", "_premain.mp4"
    ]
    run(cmd)
    append_logo("_premain.mp4", opts)

# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY - RESTAURATION DE LA LOGIQUE D'AUTO-DÉTECTION
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    opts = DEFAULTS.copy()
    
    # 1. Charger p.json si présent, sinon chercher le dernier .json
    config_file = "p.json"
    if not os.path.exists(config_file):
        jsons = [f for f in os.listdir(".") if f.endswith(".json")]
        if jsons:
            jsons.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            config_file = jsons[0]
            print(f"Utilisation du config : {config_file}")

    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            vira_result = json.load(f)
            opts.update(vira_result.get("options", {}))
    else:
        vira_result = {"segments": []}
        print("Attention: Pas de fichier JSON trouvé, utilisation des défauts.")

    # 2. Détection des fichiers _raw_*.mp4
    raw_paths = [f for f in os.listdir(".") if f.startswith("_raw_") and f.endswith(".mp4")]
    raw_paths.sort(key=lambda x: int(re.search(r'_raw_(\d+)', x).group(1)) if re.search(r'_raw_(\d+)', x) else 0)

    if not raw_paths:
        print("Erreur: Aucun fichier _raw_0.mp4, etc. trouvé.")
        sys.exit(1)

    n = len(raw_paths)
    print(f"Démarrage du rendu : {n} clips détectés.")

    # 3. Calcul des durées (on simplifie ici mais on garde la structure)
    segments = []
    for i, src in enumerate(raw_paths):
        out = f"_cin_{i}.mp4"
        # On essaie de récupérer la durée cible depuis le JSON si possible
        sdur = 3.0 # Défaut
        if "segments" in vira_result and i < len(vira_result["segments"]):
            sdur = vira_result["segments"][i].get("duration", 3.0)
            
        role = "core"
        if i == 0: role = "hook"
        elif i == n - 1: role = "punch"
        
        print(f"  [Segment {i+1}/{n} rôle={role.upper()}]")
        build_cinema_segment(src, out, sdur, 1.0, opts, role=role)
        segments.append(out)

    # 4. Finalisation
    assemble_cinema(segments, opts)
    build_cinema_overlay_no_text(opts)
    
    print("\n✅ Rendu terminé : output.mp4")

