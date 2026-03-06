import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction et Normalisation
    files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"r{i}.mp4"
        with open(name, "wb") as fout: fout.write(base64.b64decode(v['data']))
        # On force le format vertical 1080x1920 dès l'entrée
        os.system(f"ffmpeg -i {name} -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920' -c:v libx264 -preset ultrafast n{i}.mp4")
        files.append(f"n{i}.mp4")

    if len(files) < 3: return

    # --- ÉTAPE A : LE HOOK (Zoom Dynamique) ---
    # Un zoom rapide "in-and-out" pour captiver l'œil immédiatement
    os.system(f"ffmpeg -i {files[0]} -t 1.8 -vf \"zoompan=z='min(zoom+0.005,1.5)':d=1:s=1080x1920,unsharp=5:5:1.0:5:5:0.5\" -c:v libx264 hook.mp4")

    # --- ÉTAPE B : LE CORE (Jump Cuts rythmés) ---
    # On prend 3 secondes au milieu avec une saturation boostée
    os.system(f"ffmpeg -i {files[1]} -ss 0.5 -t 3 -vf \"eq=saturation=1.4:contrast=1.1,hqdn3d\" -c:v libx264 core.mp4")

    # --- ÉTAPE C : LA PUNCHLINE (Transition Glitch) ---
    # Un effet de flash blanc au raccord pour marquer la fin
    os.system(f"ffmpeg -i {files[2]} -t 2.5 -vf \"fade=t=in:st=0:d=0.3:color=white,unsharp=3:3:0.8\" -c:v libx264 punch.mp4")

    # 2. ASSEMBLAGE AVEC RACCORDS "SMOOTH"
    # Utilisation d'un fondu très court (0.2s) pour simuler un raccord pro
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "core.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4")
    print("Montage Viral OK")

if __name__ == "__main__":
    start()
        "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=1.5[v01];"
        "[v01][2:v]xfade=transition=fade:duration=0.5:offset=5.0[vfinal]"
    )
    
    # Commande de fusion avec transitions et mixage audio
    cmd = (
        f"ffmpeg -i v1.mp4 -i v2.mp4 -i v3.mp4 -filter_complex \"{filter_complex}\" "
        "-map \"[vfinal]\" -c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    os.system(cmd)
    print("Montage intelligent terminé.")

if __name__ == "__main__":
    start()
    dur_last = get_duration(files[-1])
    start_punch = max(0, dur_last - 2.5)
    os.system(f"ffmpeg -ss {start_punch} -i {files[-1]} -t 2.5 -vf \"{vf_base},fade=t=in:st=0:d=0.2:color=white\" -c:v libx264 -preset superfast punch.mp4")

    # 3. ASSEMBLAGE FINAL
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "core.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p -crf 23 output.mp4")
    print("Montage Viral terminé.")

if __name__ == "__main__":
    start()
