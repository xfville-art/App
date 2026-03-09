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

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        out = f"s{i}.mp4"
        # MODIFICATION : On enlève '-an' et on ajoute '-c:a aac' pour garder le son
        # On utilise scale/crop pour le visuel
        vf = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"
        
        # Commande FFmpeg qui préserve l'audio de chaque clip
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac -ar 44100 {out}')
        processed.append(out)

    # 2. Concaténation de la VIDÉO et de l'AUDIO
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    
    # L'option '-f concat' doit inclure l'audio, donc on ne met pas '-c copy' si les formats audio diffèrent
    run("ffmpeg -y -f concat -i l.txt -c:v copy -c:a aac output_with_sound.mp4")

    # 3. Finalisation (Logo + Fade Out)
    # On s'assure de ne pas perdre le son lors de l'ajout du logo
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=35:fontcolor=white@0.3:x=w-text_w-50:y=100"
    
    final_cmd = (
        f"ffmpeg -y -i output_with_sound.mp4 -vf \"{brand},fade=t=out:st={CFG['total_dur']-1}:d=1\" "
        f"-c:v libx264 -c:a copy output.mp4"
    )
    run(final_cmd)
    
    if os.path.exists("output.mp4"):
        print("✅ Rendu terminé : Audio d'origine conservé et mixé.")

if __name__ == "__main__":
    start()
