"""
render.py — ViraCut Studio v14  ★ LesCrados.Ai Edition ★
═════════════════════════════════════════════════════════
v14.1 : FIX OPTIMISATION SCANLINES (GEQ FILTER)
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
    print(f"    $ {' '.join(cmd[:10])}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"STDERR: {r.stderr}")
        raise RuntimeError(f"FFmpeg failed (code {r.returncode})")
    return r

# ═══════════════════════════════════════════════════════════════════════
# LOGO SPLASH (LA FONCTION CORRIGÉE)
# ═══════════════════════════════════════════════════════════════════════

def build_logo_splash(output, opts):
    """Génère l'intro/outro avec logo et effet CRT optimisé."""
    Wi, Hi = 720, 1280
    
    # Textes depuis les options
    l1 = opts.get("logo_l1", "VIRACUT").upper()
    l2 = opts.get("logo_l2", "STUDIO").upper()
    l3 = opts.get("logo_l3", "V14").upper()
    slogan = opts.get("slogan", "AI GENERATED CONTENT").upper()

    # Filtres de base
    bg_filter = "color=c=black:s=720x1280:d=2.5[bg]"
    dt_l1 = f"drawtext=fontfile={FONT}:text='{l1}':fontcolor=white:fontsize=110:x=(w-tw)/2:y=480:alpha='if(lt(t,0.5),0,if(lt(t,1), (t-0.5)/0.5, 1))'"
    dt_l2 = f"drawtext=fontfile={FONT}:text='{l2}':fontcolor=white:fontsize=110:x=(w-tw)/2:y=590:alpha='if(lt(t,0.7),0,if(lt(t,1.2), (t-0.7)/0.5, 1))'"
    dt_l3 = f"drawtext=fontfile={FONT}:text='{l3}':fontcolor=white:fontsize=40:x=(w-tw)/2+240:y=610:alpha='if(lt(t,1),0,1)'"
    dt_line = f"drawbox=x=(w-200)/2:y=740:w=200:h=3:color=white@0.8:t=fill:enable='gt(t,1.2)'"

    # Slogan (lettre par lettre sim)
    dt_slogan_parts = []
    for i, char in enumerate(slogan):
        delay = 1.4 + (i * 0.04)
        dt_slogan_parts.append(f"drawtext=fontfile={FONT}:text='{char}':fontcolor=white@0.7:fontsize=28:x=(w-300)/2 + {i*18}:y=780:enable='gt(t,{delay})'")

    # --- OPTIMISATION ICI ---
    # Au lieu de 300 drawbox, on utilise un seul filtre mathématique 'geq'
    # mod(Y,4) cible une ligne sur 4. On multiplie la luminosité par 0.75 pour l'effet scanline.
    scanline_filter = "geq=lum='if(mod(Y,4),lum(X,Y),lum(X,Y)*0.75)'"

    vignette_parts = [
        "drawbox=y=0:h=129:c=black@0.55:t=fill",
        f"drawbox=y={Hi-129}:h=129:c=black@0.55:t=fill",
        "drawbox=x=0:w=129:h=1280:c=black@0.40:t=fill",
        f"drawbox=x={Wi-129}:w=129:h=1280:c=black@0.40:t=fill"
    ]

    # Construction de la chaîne de filtres
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
    """Ajoute le splash à la fin de la vidéo."""
    build_logo_splash("_logo.mp4", opts)
    
    with open("_concat_logo.txt", "w") as f:
        f.write(f"file '{video_in}'\n")
        f.write("file '_logo.mp4'\n")
        
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_concat_logo.txt", "-c", "copy", "output.mp4"]
    run(cmd)

# ═══════════════════════════════════════════════════════════════════════
# ENGINE CORE (SIMPLIFIÉ POUR LA RÉPONSE)
# ═══════════════════════════════════════════════════════════════════════

def build_cinema_segment(src, out, duration, zoom_speed, opts, role="core"):
    """Prépare un clip individuel (color grading + zoom)."""
    # Ex: saturation 1.18, contrast 1.15
    vf = f"fps=24,eq=saturation=1.18:brightness=-0.01:contrast=1.15,zoompan=z='min(zoom+0.0015,1.5)':d={int(duration*24)}:s=720x1280"
    cmd = ["ffmpeg", "-y", "-t", str(duration), "-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "18", out]
    run(cmd)
    return out

def assemble_cinema(segments, opts):
    """Assemble les segments avec concat."""
    with open("_concat.txt", "w") as f:
        for s in segments:
            f.write(f"file '{s}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "_concat.txt", "-c", "copy", "_assembled.mp4"]
    run(cmd)

def build_cinema_overlay_no_text(opts):
    """Ajoute les bandes noires cinéma sur la vidéo assemblée."""
    cmd = [
        "ffmpeg", "-y", "-i", "_assembled.mp4",
        "-vf", "drawbox=y=0:h=65:c=black@1:t=fill,drawbox=y=1215:h=65:c=black@1:t=fill",
        "-c:v", "libx264", "-crf", "18", "_premain.mp4"
    ]
    run(cmd)
    append_logo("_premain.mp4", opts)

# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Simulation d'options pour l'exemple
    options = DEFAULTS.copy()
    
    # Vérification présence fichiers raw
    raw_files = [f for f in os.listdir(".") if f.startswith("_raw_") and f.endswith(".mp4")]
    raw_files.sort()
    
    if not raw_files:
        print("Erreur: Aucun fichier _raw_0.mp4, etc. trouvé.")
        sys.exit(1)
        
    print(f"Traitement de {len(raw_files)} clips...")
    
    processed = []
    for i, f in enumerate(raw_files):
        out_name = f"_cin_{i}.mp4"
        # On assume 3s par clip pour la démo
        processed.append(build_cinema_segment(f, out_name, 3.0, 1.0, options))
        
    assemble_cinema(processed, options)
    build_cinema_overlay_no_text(options)
    
    print("\n✅ Rendu terminé : output.mp4")
