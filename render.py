"""
render.py — ViraCut Studio v7
═══════════════════════════════════════════════════════
FIX : Suppression totale des zooms (Ken Burns)
FIX : Suppression de la banderole (Plein écran uniquement)
"""
import json, base64, os, subprocess, sys

# CONFIGURATION PAR DÉFAUT
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
DEFAULTS = {
    "resolution": "720x1280", 
    "fps": 24, 
    "crf": 18,
    "cinema_dur": 26, 
    "cinema_xfade": 0.8
}

def cfg(opts, key):
    return opts.get(key, DEFAULTS.get(key))

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print("Erreur FFmpeg:", r.stderr)
    return r.stdout

def build_segment(src, seg_out, clip_dur, opts):
    W, H = cfg(opts, "resolution").split("x")
    # Filtre simple : Mise à l'échelle pour remplir l'écran + Recadrage au centre
    vf = f"scale=hd720:force_original_aspect_ratio=increase,crop={W}:{H},fps={cfg(opts,'fps')}"
    
    cmd = f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -vf "{vf}" -c:v libx264 -crf {cfg(opts,"crf")} -pix_fmt yuv420p "{seg_out}"'
    run(cmd)

def assemble(seg_paths, opts):
    inputs = " ".join(f'-i "{p}"' for p in seg_paths)
    # Pour faire simple sans zoom ni transitions complexes qui causent des alertes
    filter_complex = "".join([f"[{i}:v][{i}:a]" for i in range(len(seg_paths))]) + f"concat=n={len(seg_paths)}:v=1:a=1[v][a]"
    cmd = f'ffmpeg -y {inputs} -filter_complex "{filter_complex}" -map "[v]" -map "[a]" -c:v libx264 -crf {cfg(opts,"crf")} output.mp4'
    run(cmd)

def start():
    if not os.path.exists("p.json"): return
    with open("p.json") as f: data = json.load(f)
    clips = data.get("videos", []); opts = data.get("options", {})
    
    raw_paths = []
    for i, v in enumerate(clips):
        p = f"_raw_{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v["data"]))
        raw_paths.append(p)

    clip_dur = cfg(opts, "cinema_dur") / len(raw_paths)
    seg_paths = []
    for i, src in enumerate(raw_paths):
        out = f"_seg_{i}.mp4"
        build_segment(src, out, clip_dur, opts)
        seg_paths.append(out)

    assemble(seg_paths, opts)
    print("Vidéo générée : output.mp4")

if __name__ == "__main__":
    start()
