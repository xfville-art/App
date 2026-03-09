import json, base64, os, subprocess

CFG = {"total_dur": 26.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    num = len(videos)
    dur_seg = CFG["total_dur"] / num
    processed = []

    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        out = f"s{i}.mp4"
        # AMÉLIORATION VISUELLE :
        # 1. 'unsharp' : pour rendre les détails de l'IA plus croustillants (netteté).
        # 2. 'vignette' : pour focaliser l'attention sur le centre du personnage.
        # 3. 'fade' : fondu entrant/sortant sur chaque clip pour la fluidité.
        vf = (f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              f"unsharp=3:3:1.5:3:3:0.5,vignette=angle=0.3,"
              f"fade=t=in:st=0:d=0.4,fade=t=out:st={dur_seg-0.4}:d=0.4")
        
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 -c:a aac -ar 44100 {out}')
        processed.append(out)

    # Concaténation (Vidéo + Audio)
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c:v copy -c:a aac temp_final.mp4")

    # Finalisation : Logo discret + Fondu final
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=35:fontcolor=white@0.3:x=w-text_w-50:y=100"
    
    final_cmd = (
        f"ffmpeg -y -i temp_final.mp4 -vf \"{brand},fade=t=out:st={CFG['total_dur']-1}:d=1\" "
        f"-c:v libx264 -c:a copy output.mp4"
    )
    run(final_cmd)
    print("✅ Rendu v23 terminé : Netteté améliorée, Vignette et Synchro Audio.")

if __name__ == "__main__":
    start()
