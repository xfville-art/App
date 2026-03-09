import json, base64, os, subprocess

CFG = {"total_dur": 26.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    dur_seg = CFG["total_dur"] / len(videos)
    processed = []

    # 1. Traitement des clips (Vidéo seule)
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        out = f"s{i}.mp4"
        vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        # On force la suppression de tout vieil audio corrompu avec -an
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -an {out}')
        processed.append(out)

    # 2. Concaténation de la vidéo muette
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c copy silent_video.mp4")

    # 3. GÉNÉRATION AUDIO (Le correctif)
    # On crée une nappe sonore "Dark Ambient" directement via FFmpeg
    # anoisesrc crée le son, extrinsically mixé avec un filtre sine pour un drone profond
    audio_gen = (
        "ffmpeg -y -f lavfi -i \"anoisesrc=d=26:c=brown:amp=0.06,lowpass=f=300\" "
        "-c:a aac -b:a 128k noise.m4a"
    )
    run(audio_gen)

    # 4. ASSEMBLAGE FINAL (Video + Audio + Watermark)
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=35:fontcolor=white@0.3:x=w-text_w-50:y=100"
    
    # -shortest assure que tout s'arrête en même temps
    final_cmd = (
        f"ffmpeg -y -i silent_video.mp4 -i noise.m4a "
        f"-vf \"{brand},fade=t=out:st=25:d=1\" "
        f"-map 0:v:0 -map 1:a:0 -c:v libx264 -c:a copy -shortest output.mp4"
    )
    run(final_cmd)
    
    if os.path.exists("output.mp4"):
        print("✅ Rendu v22 terminé avec AMBIANCE SONORE.")

if __name__ == "__main__":
    start()
