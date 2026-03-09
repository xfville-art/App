import json, base64, os, subprocess, urllib.request, time

# CONFIGURATION STRICTE
CFG = {"hook_dur": 3.0, "punch_dur": 4.0, "fps": 24}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def run(cmd):
    print(f"  ▸ Exécution FFmpeg...")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    # 1. Extraction des vidéos (On décode les fichiers envoyés par l'App)
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"raw_{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)
    
    if len(clips) < 2: 
        print("❌ Erreur: Pas assez de vidéos dans p.json"); return

    # 2. Création des segments verticaux (Cadrage 9:16 forcé)
    # On utilise un filtre simple de redimensionnement et de remplissage (pad) 
    # pour éviter les erreurs de calcul de pixels
    vf_vertical = "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"
    
    print("[1/2] Normalisation des clips...")
    # On crée s0.mp4 et s1.mp4 avec une piste audio AAC forcée
    run(f'ffmpeg -y -i {clips[0]} -t {CFG["hook_dur"]} -vf "{vf_vertical}" -r {CFG["fps"]} -c:v libx264 -pix_fmt yuv420p -c:a aac -ac 2 -ar 44100 s0.mp4')
    run(f'ffmpeg -y -i {clips[-1]} -t {CFG["punch_dur"]} -vf "{vf_vertical}" -r {CFG["fps"]} -c:v libx264 -pix_fmt yuv420p -c:a aac -ac 2 -ar 44100 s1.mp4')

    # 3. Assemblage Final (Méthode la plus stable au monde : concat demuxer)
    print("[2/2] Assemblage final et textes...")
    
    # Création du fichier de liste pour FFmpeg
    with open("list.txt", "w") as f:
        f.write("file 's0.mp4'\nfile 's1.mp4'")

    # Commande finale avec les textes
    # On ajoute des bordures noires au texte pour qu'il soit lisible partout
    cmd_final = (
        f"ffmpeg -y -f concat -i list.txt -vf "
        f"\"drawtext=text='ATTENDS LA FIN':fontfile={FONT}:fontsize=80:fontcolor=white:borderw=4:bordercolor=black:x=(w-text_w)/2:y=200:enable='between(t,0,3)', "
        f"drawtext=text='INCROYABLE':fontfile={FONT}:fontsize=70:fontcolor=yellow:borderw=4:bordercolor=black:x=(w-text_w)/2:y=h-300:enable='between(t,3,10)'\" "
        f"-c:v libx264 -crf 18 -c:a aac -pix_fmt yuv420p output.mp4"
    )
    
    result = run(cmd_final)

    if os.path.exists("output.mp4"):
        print("✅ SUCCESS: output.mp4 généré.")
    else:
        print(f"❌ FFmpeg a échoué. Log d'erreur: {result.stderr}")

if __name__ == "__main__":
    start()
