import json, base64, os, subprocess, urllib.request, time

# ─────────────────────────────────────────────────────────────────────
#  CONFIG VERTICALE & AUDIO
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "hook_dur": 3.5,
    "punch_dur": 4.5,
    "zoom_scale": 1.15,
    "res": "720:1280", # Format Vertical Strict
    "fps": 24,
    "crf": 18
}

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    print(f"  ▸ {cmd[:100]}...")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction des clips
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        path = f"raw_{i}.mp4"
        with open(path, "wb") as fout:
            fout.write(base64.b64decode(v['data']))
        clips.append(path)
    
    if len(clips) < 2: return

    # 2. Préparation des segments VERTICAUX
    # Le filtre 'setsar=1' et le 'crop' forcent le format 9:16
    vf_vertical = (
        "scale=ih*9/16:ih,scale=720:1280,setsar=1" 
    )
    
    run(f'ffmpeg -y -i {clips[0]} -t {CFG["hook_dur"]} -vf "{vf_vertical}" -c:v libx264 -an seg0.mp4')
    run(f'ffmpeg -y -i {clips[-1]} -t {CFG["punch_dur"]} -vf "{vf_vertical}" -c:v libx264 -an seg1.mp4')

    # 3. Montage Final avec Zoom + Texte
    # On récupère l'audio du premier clip pour ne pas être muet
    zoom = "zoompan=z='min(zoom+0.0015,1.2)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    
    cmd_final = (
        f"ffmpeg -y -i seg0.mp4 -i seg1.mp4 -i {clips[0]} -filter_complex "
        f"\"[0:v]{zoom}[v0]; [1:v]{zoom}[v1]; [v0][v1]concat=n=2:v=1:a=0[v]; "
        f"[v]drawtext=text='ATTENDS LA FIN':fontfile={FONT}:fontsize=80:fontcolor=white:borderw=5:x=(w-text_w)/2:y=200:enable='between(t,0,3)', "
        f"drawtext=text='INCROYABLE':fontfile={FONT}:fontsize=75:fontcolor=yellow:borderw=5:x=(w-text_w)/2:y=h-300:enable='between(t,3,10)'\" "
        f"-map \"[v]\" -map 2:a -c:v libx264 -crf {CFG['crf']} -c:a aac -shortest -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)
    if os.path.exists("output.mp4"):
        print("✅ output.mp4 généré en 720x1280 avec audio !")

if __name__ == "__main__":
    start()
