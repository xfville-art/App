import json, base64, os, subprocess

CFG = {
    "total_dur": 26.0,  # Format long
    "res": "720x1280",
    "fps": 24
}

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
        out = f"s{i}.ts" # Utilisation de .ts pour une meilleure stabilité de concaténation
        
        # 🛡️ SOLUTION AU FREEZE : 
        # 1. '-fflags +genpts' : Recrée les marqueurs de temps dès la lecture.
        # 2. 'fps=24' : Force la génération de nouvelles images pour combler les manques.
        # 3. 'format=yuv420p' : Standardise le format pour tous les lecteurs.
        vf = (f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
              f"fps={CFG['fps']},setpts=PTS-STARTPTS")
        
        cmd = (f'ffmpeg -y -fflags +genpts -i {raw} -t {dur_seg} -vf "{vf}" '
               f'-c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -an {out}')
        run(cmd)
        processed.append(out)

    # Concaténation ultra-stable via Transport Stream
    concat_cmd = f"ffmpeg -y -i \"concat:{'|'.join(processed)}\" -c copy no_audio.mp4"
    run(concat_cmd)

    # Réintégration de l'audio d'origine (sur toute la longueur)
    # On prend l'audio du premier clip r0.mp4 par défaut
    final_cmd = (
        f"ffmpeg -y -i no_audio.mp4 -i r0.mp4 -map 0:v -map 1:a? "
        f"-c:v copy -c:a aac -shortest output.mp4"
    )
    
    run(final_cmd)
    print("✅ Rendu v32 terminé : Le mouvement vidéo est rétabli.")

if __name__ == "__main__":
    start()
