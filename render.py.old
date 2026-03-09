import json, base64, os, subprocess

# On passe à 30 secondes pour un rythme plus posé et qualitatif
CFG = {"total_dur": 30.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips_data = data.get('videos', [])
    num_clips = len(clips_data)
    # Durée plus longue par segment (environ 7.5s pour 4 clips)
    dur = CFG["total_dur"] / num_clips
    
    processed = []
    for i, v in enumerate(clips_data):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        out = f"s{i}.mp4"
        # On retire tout zoom et on applique un léger fondu au noir au début/fin de chaque clip
        vf = (f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              f"fade=t=in:st=0:d=0.5,fade=t=out:st={dur-0.5}:d=0.5")
        
        run(f'ffmpeg -y -i {raw} -t {dur} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac {out}')
        processed.append(out)

    # Assemblage propre
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # Signature discrète uniquement (Watermark)
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=35:fontcolor=white@0.4:x=w-text_w-50:y=80"
    
    # Rendu final sans texte central et avec une fin progressive
    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},fade=t=out:st=29:d=1\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(final_cmd)
    print("✅ Rendu v18 terminé : Montage épuré et cinématique.")

if __name__ == "__main__":
    start()
