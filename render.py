import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction et sécurisation
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout: 
            fout.write(base64.b64decode(v['data']))

    # Configuration Élite : Netteté (unsharp) + Saturation (1.4)
    vf_base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:1.0:5:5:0.5,eq=saturation=1.4"

    # --- CLIP 1 : LE HOOK (Accroche) ---
    # Zoom progressif pour aspirer le regard
    os.system(f"ffmpeg -i r0.mp4 -t 1.5 -vf \"{vf_base},zoompan=z='min(zoom+0.002,1.5)':d=1:s=1080x1920\" -c:v libx264 -preset ultrafast h.mp4")

    # --- CLIP 2 : LE CORE (Intelligence de raccord) ---
    # On saute 0.3s au début pour supprimer le temps mort et on zoom de 10%
    # Cet effet de "Jump Cut" donne un aspect montage pro instantané
    os.system(f"ffmpeg -ss 0.3 -i r1.mp4 -t 3.0 -vf \"{vf_base},scale=1.1*iw:-1,crop=iw/1.1:ih/1.1\" -c:v libx264 -preset ultrafast c.mp4")

    # --- CLIP 3 : LA PUNCHLINE (Impact) ---
    # Retour au plan large avec un flash blanc au raccord pour marquer la fin
    os.system(f"ffmpeg -i r2.mp4 -t 2.5 -vf \"{vf_base},fade=t=in:st=0:d=0.2:color=white\" -c:v libx264 -preset ultrafast p.mp4")

    # 3. ASSEMBLAGE FINAL SÉCURISÉ
    with open("list.txt", "w") as f:
        for m in ["h.mp4", "c.mp4", "p.mp4"]:
            if os.path.exists(m): f.write(f"file '{m}'\n")
    
    # Encodage final compatible avec tous les téléphones
    os.system("ffmpeg -f concat -safe 0 -i list.txt -c:v libx264 -pix_fmt yuv420p output.mp4")
    
