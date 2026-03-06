import json, base64, os, subprocess

def start():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f: data = json.load(f)

    # 1. Extraction et formatage (Normalisation en 1080x1920)
    for i, v in enumerate(data.get('videos', [])):
        with open(f"r{i}.mp4", "wb") as fout: fout.write(base64.b64decode(v['data']))

    # Configuration visuelle : Netteté + Saturation pour le look "Viral"
    vf_base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,unsharp=5:5:1.0,eq=saturation=1.3"

    # --- ÉTAPE A : LE HOOK (1.5s) ---
    # Zoom progressif pour "aspirer" le spectateur
    os.system(f"ffmpeg -i r0.mp4 -t 1.5 -vf \"{vf_base},zoompan=z='min(zoom+0.002,1.5)':d=1:s=1080x1920\" -c:v libx264 -preset ultrafast h.mp4")

    # --- ÉTAPE B : LE CORE (3.5s) ---
    # On commence 0.2s plus tard pour couper le silence de prise
    os.system(f"ffmpeg -ss 0.2 -i r1.mp4 -t 3.5 -vf \"{vf_base}\" -c:v libx264 -preset ultrafast c.mp4")

    # --- ÉTAPE C : LA PUNCHLINE (2.5s) ---
    # Zoom d'impact (Jump Cut) + Transition flash blanc
    os.system(f"ffmpeg -i r2.mp4 -t 2.5 -vf \"{vf_base},zoompan=z=1.1:x=iw/4:y=ih/4:d=1:s=1080x1920,fade=t=in:st=0:d=0.2:color=white\" -c:v libx264 -preset ultrafast p.mp4")

    # 3. ASSEMBLAGE AVEC RACCORDS FLUIDES (Crossfade de 0.2s)
    filter_complex = (
        "[0:v][1:v]xfade=transition=fade:duration=0.2:offset=1.3[v01];"
        "[v01][2:v]xfade=transition=fade:duration=0.2:offset=4.6[vfinal]"
    )
    
    os.system(f"ffmpeg -i h.mp4 -i c.mp4 -i p.mp4 -filter_complex \"{filter_complex}\" -map \"[vfinal]\" -c:v libx264 -pix_fmt yuv420p output.mp4")
    
