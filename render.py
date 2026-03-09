import json, base64, os, subprocess, re

CFG = {"total_dur": 28.0, "res": "720x1280", "fps": 24}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    videos = data.get('videos', [])
    num = len(videos)
    # On allonge un peu chaque clip pour permettre le chevauchement des transitions
    dur_seg = (CFG["total_dur"] / num) + 0.5 
    
    processed = []
    for i, v in enumerate(videos):
        raw = f"r{i}.mp4"
        with open(raw, "wb") as f: f.write(base64.b64decode(v['data']))
        
        out = f"s{i}.mp4"
        # 1. Zoom très subtil (1.02) pour donner de la vie sans déborder
        # 2. Fondu entrant/sortant sur chaque clip pour la fluidité
        vf = (f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              f"zoompan=z='1.03':d=1:s=720x1280,fade=t=in:st=0:d=0.5,fade=t=out:st={dur_seg-0.5}:d=0.5")
        
        run(f'ffmpeg -y -i {raw} -t {dur_seg} -vf "{vf}" -c:v libx264 -crf 18 -an {out}')
        processed.append(out)

    # Assemblage
    with open("l.txt", "w") as f:
        for c in processed: f.write(f"file '{c}'\n")
    run("ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # Finalisation : Logo discret + Fondu final au noir
    brand = f"drawtext=text='@LesCrados.ai':fontfile={FONT}:fontsize=35:fontcolor=white@0.3:x=w-text_w-50:y=100:borderw=2:bordercolor=black@0.3"
    
    final_cmd = (
        f"ffmpeg -y -i base.mp4 -vf \"{brand},fade=t=out:st={CFG['total_dur']-1}:d=1\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(final_cmd)
    print("✅ Montage Masterpiece terminé.")

if __name__ == "__main__":
    start()
