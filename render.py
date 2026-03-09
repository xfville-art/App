import json, base64, os, subprocess, urllib.request, time

# CONFIGURATION ÉMOTIONNELLE
CFG = {"hook_dur": 3.5, "punch_dur": 4.5, "res": "720x1280", "fps": 24}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    print(f"  ▸ Exécution...")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0: print(f"  ❌ Erreur: {r.stderr[:200]}")
    return r

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction des vidéos
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"raw_{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)
    
    # 2. Création des segments verticaux (Plus robuste)
    # On force l'encodage audio en AAC même si c'est du silence pour éviter les erreurs de mapping
    vf = "scale=ih*9/16:ih,crop=h*9/16:h,scale=720:1280,setsar=1"
    
    print("[1/3] Préparation des clips...")
    run(f'ffmpeg -y -i {clips[0]} -t {CFG["hook_dur"]} -vf "{vf}" -r {CFG["fps"]} -c:v libx264 -c:a aac -ar 44100 s0.mp4')
    run(f'ffmpeg -y -i {clips[-1]} -t {CFG["punch_dur"]} -vf "{vf}" -r {CFG["fps"]} -c:v libx264 -c:a aac -ar 44100 s1.mp4')

    # 3. Assemblage Final avec Textes (Sans Zoompan complexe pour l'instant)
    # Le Zoompan est remplacé par un scale dynamique plus stable
    print("[2/3] Montage final...")
    
    # Texte : On simplifie pour éviter les erreurs de parsing
    h_txt = "ATTENDS LA FIN"
    p_txt = "ABONNE TOI"
    
    cmd_final = (
        f"ffmpeg -y -i s0.mp4 -i s1.mp4 -filter_complex "
        f"\"[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]; "
        f"[v]drawtext=text='{h_txt}':fontfile={FONT}:fontsize=80:fontcolor=white:borderw=5:x=(w-text_w)/2:y=200:enable='between(t,0,3)', "
        f"drawtext=text='{p_txt}':fontfile={FONT}:fontsize=70:fontcolor=yellow:borderw=5:x=(w-text_w)/2:y=h-300:enable='between(t,3,10)'\" "
        f"-map \"[v]\" -map \"[a]\" -c:v libx264 -crf 18 -pix_fmt yuv420p output.mp4"
    )
    
    run(cmd_final)

    # 4. Vérification finale
    if os.path.exists("output.mp4"):
        print("✅ SUCCESS: output.mp4 est prêt.")
    else:
        # ULTIME SECOURS : Si le montage complexe échoue, on copie juste le premier clip
        print("⚠ Fallback: Création d'une version simplifiée...")
        run(f'ffmpeg -y -i {clips[0]} -t 5 -vf "{vf}" -c:v libx264 -pix_fmt yuv420p output.mp4')

if __name__ == "__main__":
    start()
