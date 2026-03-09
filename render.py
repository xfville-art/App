import json, base64, os, subprocess

CFG = {"total_dur": 26.0, "res": "720x1280", "audio_br": 192}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    dur_seg = CFG["total_dur"] / len(videos)
    processed = []

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        # Montage propre sans texte, zoom stable
        vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 -an {out}')
        processed.append(out)

    # Assemblage vidéo
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c copy silent_base.mp4")

    # --- CORRECTION AUDIO ---
    # On génère un bruit de fond "Dark Ambient" synthétique si pas d'audio
    # Cela garantit que la vidéo n'est jamais muette
    audio_cmd = (
        f"ffmpeg -y -f lavfi -i \"anoisesrc=d={CFG['total_dur']}:c=brown:amp=0.05,lowpass=f=400,tremolo=f=0.5:d=0.8\" "
        f"-c:a aac -b:a {CFG['audio_br']}k background_audio.m4a"
    )
    run(audio_cmd)

    # Fusion Finale avec Watermark et Fade
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=35:fontcolor=white@0.3:x=w-text_w-50:y=100"
    final_cmd = (
        f"ffmpeg -y -i silent_base.mp4 -i background_audio.m4a "
        f"-vf \"{brand},fade=t=out:st={CFG['total_dur']-1}:d=1\" "
        f"-map 0:v -map 1:a -c:v libx264 -c:a copy -shortest output.mp4"
    )
    run(final_cmd)
    print("✅ Rendu v21 terminé avec restauration du son.")

if __name__ == "__main__":
    start()
