import json
import base64
import os

def start():
    print("--- DÉMARRAGE DU RENDU VIRACUT ---")
    
    # 1. Lecture du fichier p.json envoyé par le téléphone
    if not os.path.exists('p.json'):
        print("Erreur : p.json introuvable !")
        return

    try:
        with open('p.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Erreur de lecture JSON : {e}")
        return

    # 2. Décodage des vidéos
    input_files = []
    for i, v in enumerate(data.get('videos', [])):
        name = f"vid_{i}.mp4"
        with open(name, "wb") as f_out:
            # On décode le texte base64 en vraie vidéo
            f_out.write(base64.b64decode(v['data']))
        input_files.append(name)
        print(f"Vidéo {i} prête pour le montage")

    # 3. Montage FFmpeg (ici on prend la 1ère vidéo pour tester)
    if input_files:
        print("Exécution de FFmpeg...")
        # Cette ligne crée la vidéo finale nommée output.mp4
        os.system(f"ffmpeg -i {input_files[0]} -y -c copy output.mp4")
        print("SUCCÈS : output.mp4 a été généré.")
    else:
        print("Aucune vidéo à traiter.")

if __name__ == "__main__":
    start()
                  
