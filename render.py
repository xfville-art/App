"""
render.py — ViraCut Studio v9  ★ LesCrados.Ai Edition ★
"""
import json, base64, os, subprocess, sys, re

# ... [CONFIG EXISTANTE] ...

# ═══════════════════════════════════════════════════════════════════════
# VITALITY AI ANALYSIS (NOUVEAU)
# ═══════════════════════════════════════════════════════════════════════

def analyze_virality(path):
    """
    Simule une analyse IA du potentiel de rétention.
    Basé sur le dynamisme audio, la densité visuelle et la durée optimale.
    """
    dur = duration(path)
    audio = has_audio(path)
    
    # Score de base
    score = 45 
    
    # Bonus Audio : Les vidéos avec son captent mieux l'attention
    if audio: score += 20
    
    # Bonus Durée : Les clips de 5-12s sont le "sweet spot" pour la rétention
    if 5 <= dur <= 12: score += 15
    elif dur > 20: score -= 10 # Trop long = risque de décrochage
    
    # Bonus Mouvement : Analyse de la complexité du bitrate (mouvement caméra/sujet)
    try:
        file_size = os.path.getsize(path)
        bitrate = file_size / (dur + 0.1)
        if bitrate > 1500000: score += 18 # Haute densité d'information visuelle
    except: pass

    return min(score, 98) # Jamais 100% pour laisser place à l'humain

# ═══════════════════════════════════════════════════════════════════════
# MAIN ENGINE MODIFICATION
# ═══════════════════════════════════════════════════════════════════════

def main():
    # ... [LOGIQUE DE DECODAGE EXISTANTE] ...
    
    # Analyse de vitalité pour chaque clip reçu
    for i, p in enumerate(raw_paths):
        v_score = analyze_virality(p)
        print(f"  Clip {i} Vitality Score: {v_score}%")
        # Ce score est renvoyé à l'interface via les logs ou metadata
