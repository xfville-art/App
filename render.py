import json, base64, os, subprocess, time

def update_progress(text):
    with open("progress.txt", "w") as f:
        f.write(text)

def main():
    if not os.path.exists('p.json'): return
    with open('p.json', 'r') as f:
        raw = json.load(f)
        data = json.loads(base64.b64decode(raw['content']))

    videos = data.get('videos', [])
    processed = []
    
    for i, v in enumerate(videos):
        in_f, out_f = f"i_{i}.mp4", f"o_{i}.ts"
        with open(in_f, "wb") as f: f.write(base64.b64decode(v['data']))
        
        # Commande avec monitoring de progression
        cmd = [
            'ffmpeg', '-y', '-i', in_f,
            '-vf', f"scale=720:1280,drawtext=text='{v.get('text','')}':fontcolor={v.get('color','yellow')}:fontsize=80:x=(w-text_w)/2:y=(h-text_h)/2",
            '-c:v', 'libx264', '-preset', 'ultrafast', '-progress', 'pipe:1', out_f
        ]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        
        for line in process.stdout:
            if "out_time_ms" in line:
                update_progress(f"Clip {i+1}/{len(videos)} - {line.strip()}")

        process.wait()
        processed.append(out_f)

    # Fusion finale
    with open('list.txt', 'w') as f:
        for n in processed: f.write(f"file '{n}'\n")
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c:v', 'copy', 'output.mp4'])
    update_progress("COMPLETED")

if __name__ == "__main__":
    main()
