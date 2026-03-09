import json, base64, os, subprocess, urllib.request, re

CFG = {"total_dur": 25.0, "res": "720x1280"}
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_ai_script(frame_b64):
    # Demande à Gemini des textes ultra-courts (impact maximum)
    prompt = "Donne 3 textes viraux (3 mots max). JSON: {\"h\": \"...\", \"m\": \"...\", \"p\": \"...\"}"
    # ... (code de requête Gemini habituel)
    return {"h": "ARRÊTE TOUT", "m": "REGARDE BIEN", "p": "ABONNE-TOI"} # Fallback

def start():
    if not os.path.exists('p.json'): return
    with open('p.json') as f: data = json.load(f)
    
    clips = []
    for i, v in enumerate(data.get('videos', [])):
        p = f"r{i}.mp4"
        with open(p, "wb") as f: f.write(base64.b64decode(v['data']))
        clips.append(p)

    ai = get_ai_script("") # À connecter avec ta logique de frame

    # 1. Rendu des Segments avec JUMP CUTS & FLASH
    segs = []
    dur = CFG["total_dur"] / len(clips)
    for i, cp in enumerate(clips):
        out = f"s{i}.mp4"
        # Alternance de zoom : Normal -> Zoomé -> Très Zoomé
        z = [1.0, 1.2, 1.4][i % 3]
        # Ajout d'un fondu au blanc (fade) pour dynamiser la transition
        vf = f"scale=1280:1280,crop=720:1280,scale=iw*{z}:ih*{z},crop=720:1280,fade=t=in:st=0:d=0.3:color=white"
        run(f'ffmpeg -y -i {cp} -t {dur} -vf "{vf}" -c:v libx264 -crf 20 -c:a aac s{i}.mp4')
        segs.append(out)

    # 2. Assemblage & Textes Dynamiques
    with open("l.txt", "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    run(f"ffmpeg -y -f concat -i l.txt -c copy base.mp4")

    # Style : Bordure énorme pour la lisibilité
    draw = f"fontfile={FONT}:borderw=12:bordercolor=black:x=(w-text_w)/2"
    
    cmd_final = (
        f"ffmpeg -y -i base.mp4 -vf "
        f"\"drawtext=text='{ai['h']}':{draw}:fontsize=115:fontcolor=white:y=280:enable='between(t,0,4)', "
        f"drawtext=text='{ai['m']}':{draw}:fontsize=100:fontcolor=yellow:y=h/2:enable='between(t,6,12)', "
        f"drawtext=text='LIKE ET COMMENTE':{draw}:fontsize=85:fontcolor=white:y=h-450:enable='between(t,15,20)', "
        f"drawtext=text='{ai['p']}':{draw}:fontsize=105:fontcolor=white:y=h-250:enable='between(t,21,25)'\" "
        f"-c:v libx264 -pix_fmt yuv420p output.mp4"
    )
    run(cmd_final)

if __name__ == "__main__":
    start()
