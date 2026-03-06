import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout: fout.write(base64.b64decode(v['data']))

    # --- 1. LE HOOK : "L'ACCROCHE ÉLECTRIQUE" (1.5s) ---
    # Zoom saccadé + Saturation + Netteté forcée
    os.system("ffmpeg -i r0.mp4 -t 1.5 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:1.5,eq=saturation=1.6:contrast=1.2,zoompan=z='pzoom+0.005':d=1:s=1080x1920' -c:v libx264 -preset ultrafast hook.mp4")

    # --- 2. LE CORE : "LE RYTHME JUMP-CUT" (3s) ---
    # On coupe les silences/morts pour ne garder que l'énergie
    os.system("ffmpeg -i r1.mp4 -ss 0.5 -t 1.5 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=saturation=1.3' -c:v libx264 -preset ultrafast c1.mp4")
    os.system("ffmpeg -i r1.mp4 -ss 2.5 -t 1.5 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z=1.1:s=1080x1920' -c:v libx264 -preset ultrafast c2.mp4")

    # --- 3. LA PUNCHLINE : "L'IMPACT FINAL" (2s) ---
    # Effet de vignettage (bords sombres) pour focaliser sur le centre
    os.system("ffmpeg -i r2.mp4 -t 2 -vf 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,vignette=PI/4,fade=t=in:st=0:d=0.2:color=white' -c:v libx264 -preset ultrafast punch.mp4")

    # --- 4. ASSEMBLAGE ET RACCORD INTELLIGENT ---
    with open("list.txt", "w") as f:
        for m in ["hook.mp4", "c1.mp4", "c2.mp4", "punch.mp4"]: f.write(f"file '{m}'\n")
    
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4")
    
    if os.path.exists("output.mp4"):
        with open("output.mp4", "rb") as f:
            res_b64 = base64.b64encode(f.read()).decode()
        with open("result.json", "w") as f:
            json.dump({"video": res_b64}, f)
