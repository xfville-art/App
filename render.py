"""
render.py — ViraCut Studio v7  ★ LesCrados.Ai Edition ★
═══════════════════════════════════════════════════════
FIX : Suppression totale de l'IA et de la génération de texte
FIX : Correction de l'erreur NameError: 'text_h'
"""
import json, base64, os, subprocess, urllib.request, urllib.error
import time, sys, random, hashlib

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

DEFAULTS = {
    "mode": "auto", "resolution": "720x1280", "fps": 24, "crf": 18,
    "audio_br": 192, "fade_dur": 0.3, 
    "cinema_dur": 26, "cinema_clip_min": 7, "cinema_clip_max": 12,
    "cinema_xfade": 0.8, "cinema_kb_zoom": 1.10, "cinema_lb_h": 80,
}

# ═══════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════
def cfg(opts, key):
    return opts.get(key, DEFAULTS[key])

def run(cmd, check=True):
    print(f"    $ {cmd[:115]}{'...' if len(cmd)>115 else ''}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("STDERR:", r.stderr[-800:])
        raise RuntimeError(f"FFmpeg failed (code {r.returncode})")
    return r.stdout + r.stderr

def ffprobe(path):
    cmd = f'ffprobe -v quiet -print_format json -show_format -show_streams "{path}"'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0: return {"format": {}, "streams": []}
    return json.loads(r.stdout)

def duration(path):
    d = ffprobe(path)
    return float(d.get("format", {}).get("duration", 0))

def has_audio(path):
    d = ffprobe(path)
    return any(s.get("codec_type") == "audio" for s in d.get("streams", []))

# ═══════════════════════════════════════════════════════════════════════
# LOGO SPLASH ANIME (FIN)
# ═══════════════════════════════════════════════════════════════════════
def build_logo_splash(out, opts):
    W, H  = cfg(opts, "resolution").split("x")
    fps   = cfg(opts, "fps"); crf = cfg(opts, "crf")
    Wi, Hi = int(W), int(H)
    dur   = 5.0
    les_sz, crados_sz, ai_sz = 78, 142, 82
    total_h   = les_sz + 18 + crados_sz + 14 + ai_sz
    block_top = (Hi - total_h) // 2
    les_y, crados_y, ai_y = block_top, block_top + les_sz + 18, block_top + les_sz + 18 + crados_sz + 22

    crad_y_expr = f"if(lt(t,0.8),{Hi},if(lt(t-0.8,0.5),{Hi}+({crados_y}-{Hi})*((t-0.8)/0.5),{crados_y}))"
    ai_y_expr = f"if(lt(t,1.7),{Hi},if(lt(t-1.7,0.4),{Hi}+({ai_y}-{Hi})*((t-1.7)/0.4),{ai_y}))"

    dt_les = f"drawtext=fontfile={FONT}:text='LES':fontsize={les_sz}:fontcolor=white:x=(w-text_w)/2:y={les_y}:enable='gte(t,0.3)'"
    dt_crad = f"drawtext=fontfile={FONT}:text='CRADOS':fontsize={crados_sz}:fontcolor=white:x=(w-text_w)/2:y='{crad_y_expr}':enable='gte(t,0.8)'"
    dt_ai = f"drawtext=fontfile={FONT}:text='.Ai':fontsize={ai_sz}:fontcolor=#FF2442:x=(w-text_w)/2:y='{ai_y_expr}':enable='gte(t,1.7)'"

    vf = f"{dt_les},{dt_crad},{dt_ai},fade=t=in:st=0:d=0.5,fade=t=out:st=4.2:d=0.8"
    run(f'ffmpeg -y -f lavfi -i "color=c=black:size={W}x{H}:rate={fps}" -f lavfi -i "anullsrc=r=44100:cl=stereo" -t {dur} -filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{dur}[a]" -map "[v]" -map "[a]" -c:v libx264 -pix_fmt yuv420p -crf {crf} "{out}"')

def append_logo(premain, opts):
    build_logo_splash("_logo.mp4", opts)
    with open("_concat_logo.txt", "w") as f:
        f.write(f"file '{premain}'\nfile '_logo.mp4'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i _concat_logo.txt -c:v libx264 -pix_fmt yuv420p -crf {cfg(opts, "crf")} output.mp4')

# ═══════════════════════════════════════════════════════════════════════
# MODES RENDU
# ═══════════════════════════════════════════════════════════════════════
def build_cinema_segment(src, seg_out, clip_dur, kb_zoom, opts):
    W, H = cfg(opts, "resolution").split("x"); fps = cfg(opts, "fps")
    scale_crop = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}"
    grade = "eq=saturation=0.9:brightness=-0.02:contrast=1.1"
    inc = (kb_zoom - 1.0) / max(clip_dur * fps, 1)
    kb = f"zoompan=z='min(zoom+{inc:.6f},{kb_zoom})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
    vf = f"{scale_crop},{grade},{kb}"
    if has_audio(src):
        run(f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -vf "{vf}" -c:v libx264 -crf {cfg(opts,"crf")} -c:a aac -shortest "{seg_out}"')
    else:
        run(f'ffmpeg -y -t {clip_dur:.2f} -i "{src}" -f lavfi -i "anullsrc" -filter_complex "[0:v]{vf}[v];[1:a]atrim=0:{clip_dur}[a]" -map "[v]" -map "[a]" -c:v libx264 -crf {cfg(opts,"crf")} "{seg_out}"')

def assemble_cinema(seg_paths, xfade_dur, opts):
    if len(seg_paths) == 1:
        run(f'cp "{seg_paths[0]}" _assembled.mp4'); return
    inputs = " ".join(f'-i "{p}"' for p in seg_paths)
    v_parts, a_parts = [], []
    offset = duration(seg_paths[0]) - xfade_dur
    prev_v, prev_a = "[0:v]", "[0:a]"
    for i in range(1, len(seg_paths)):
        nv, na = (f"[xv{i}]", f"[xa{i}]") if i < len(seg_paths)-1 else ("[vfin]", "[afin]")
        v_parts.append(f"{prev_v}[{i}:v]xfade=transition=fade:duration={xfade_dur}:offset={offset}{nv}")
        a_parts.append(f"{prev_a}[{i}:a]acrossfade=d={xfade_dur}{na}")
        offset += duration(seg_paths[i]) - xfade_dur
        prev_v, prev_a = nv, na
    run(f'ffmpeg -y {inputs} -filter_complex "{";".join(v_parts + a_parts)}" -map "[vfin]" -map "[afin]" -c:v libx264 -crf {cfg(opts,"crf")} _assembled.mp4')

def build_cinema_overlay_no_text(opts):
    W, H = cfg(opts, "resolution").split("x"); Hi = int(H)
    lb_h = cfg(opts, "cinema_lb_h")
    total = duration("_assembled.mp4")
    
    # Uniquement les bandes noires haut et bas
    lb = f"drawbox=y=0:h={lb_h}:c=black@1:t=fill,drawbox=y={Hi-lb_h}:h={lb_h}:c=black@1:t=fill"
    
    run(f'ffmpeg -y -i _assembled.mp4 -vf "{lb}" -af "afade=t=out:st={total-0.5}:d=0.5" -c:v libx264 -crf {cfg(opts,"crf")} _premain.mp4')
    append_logo("_premain.mp4", opts)

# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════
def start():
    if not os.path.exists("p.json"): sys.exit(1)
    with open("p.json") as f: data = json.load(f)
    clips_raw = data.get("videos", []); opts = data.get("options", {})
    
    print("=" * 50); print("  ViraCut v7 -- LesCrados.Ai Edition (NO TEXT)"); print("=" * 50)
    
    raw_paths = []
    for i, v in enumerate(clips_raw):
        p = f"_raw_{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v["data"]))
        raw_paths.append(p)

    n = len(raw_paths)
    target = cfg(opts, "cinema_dur")
    xf = cfg(opts, "cinema_xfade")
    clip_dur = (target - xf*(n-1)) / n
    
    seg_paths = []
    for i, src in enumerate(raw_paths):
        out = f"_cin_{i}.mp4"
        build_cinema_segment(src, out, clip_dur, cfg(opts, "cinema_kb_zoom"), opts)
        seg_paths.append(out)

    assemble_cinema(seg_paths, xf, opts)
    build_cinema_overlay_no_text(opts)
    print("\n DONE: output.mp4")

if __name__ == "__main__":
    start()
