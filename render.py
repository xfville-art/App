"""
render.py — ViraCut Studio v10
+ Vitality Analyzer
"""

import json
import os
import subprocess
import re

# ═══════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout + r.stderr


def ffprobe(path):
    cmd = f'ffprobe -v quiet -print_format json -show_format -show_streams "{path}"'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        return {}
    return json.loads(r.stdout)


def duration(path):
    data = ffprobe(path)
    try:
        return float(data["format"]["duration"])
    except:
        return 0


def has_audio(path):
    data = ffprobe(path)
    for s in data.get("streams", []):
        if s.get("codec_type") == "audio":
            return True
    return False


# ═══════════════════════════════════════════════
# DETECTION SILENCES
# ═══════════════════════════════════════════════

def detect_silences(path):

    if not has_audio(path):
        return []

    cmd = (
        f'ffmpeg -i "{path}" '
        f'-af silencedetect=noise=-35dB:d=0.15 '
        f'-f null -'
    )

    output = run(cmd)

    silences = []
    start = None

    for line in output.splitlines():

        s = re.search(r"silence_start:\s*([\d.]+)", line)
        e = re.search(r"silence_end:\s*([\d.]+)", line)

        if s:
            start = float(s.group(1))

        if e and start is not None:
            silences.append((start, float(e.group(1))))
            start = None

    return silences


# ═══════════════════════════════════════════════
# ANALYSE VITALITÉ
# ═══════════════════════════════════════════════

def motion_score(video):

    cmd = (
        f'ffmpeg -i "{video}" '
        f'-filter:v "select=gt(scene\\,0.15),metadata=print" '
        f'-f null -'
    )

    out = run(cmd)

    cuts = out.count("scene_score")

    return min(100, cuts * 6)


def audio_energy(video):

    if not has_audio(video):
        return 0

    cmd = f'ffmpeg -i "{video}" -af volumedetect -f null -'

    out = run(cmd)

    m = re.search(r"mean_volume:\s*(-?\d+)", out)

    if not m:
        return 50

    v = int(m.group(1))

    score = 100 + v

    return max(0, min(100, score))


def speech_density(video):

    silences = detect_silences(video)

    if not silences:
        return 100

    d = duration(video)

    silence_time = 0

    for s, e in silences:
        silence_time += (e - s)

    ratio = silence_time / d

    score = 100 - (ratio * 100)

    return max(0, min(100, score))


def analyze_vitality(video):

    m = motion_score(video)
    a = audio_energy(video)
    s = speech_density(video)

    vitality = (
        m * 0.4 +
        a * 0.3 +
        s * 0.3
    )

    vitality = int(vitality)

    print("──────── VITALITY ANALYSIS ────────")
    print("motion :", m)
    print("audio  :", a)
    print("speech :", s)
    print("VITALITY SCORE :", vitality)
    print("──────────────────────────────────")

    return vitality


# ═══════════════════════════════════════════════
# MONTAGE SIMPLE
# ═══════════════════════════════════════════════

def render(video, output):

    vitality = analyze_vitality(video)

    if vitality > 70:
        preset = "fast"
    elif vitality > 40:
        preset = "normal"
    else:
        preset = "cinema"

    print("Montage preset :", preset)

    cmd = f"""
    ffmpeg -y -i "{video}"
    -vf scale=720:1280
    -r 24
    -c:v libx264
    -crf 18
    -preset veryfast
    -c:a aac
    "{output}"
    """

    run(cmd)

    return {
        "output": output,
        "vitality": vitality,
        "preset": preset
    }


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

if __name__ == "__main__":

    import sys

    video = sys.argv[1]
    output = sys.argv[2]

    result = render(video, output)

    print(json.dumps(result))
