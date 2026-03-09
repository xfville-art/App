# ViraCut Studio

Montage vidéo viral automatisé — clips → GitHub Actions → FFmpeg + IA → output.mp4 9:16

---

## Architecture

```
xfville-art/App/
├── .github/
│   └── workflows/
│       └── viracut.yml     ← workflow GitHub Actions
├── render.py               ← pipeline de rendu (Python stdlib)
├── p.json                  ← payload généré par App.html
└── README.md
```

---

## Installation rapide

### 1. Créer le repo GitHub

```
Nom        : App  (ou ce que tu veux)
Visibilité : Private  ← obligatoire (contient les clips en base64)
```

### 2. Uploader les fichiers

Dans la **racine** du repo :
- `render.py`
- `README.md`
- `p.json` avec ce contenu initial :

```json
{"videos": [], "options": {}}
```

Dans `.github/workflows/` :
- `viracut.yml`

### 3. Secret ANTHROPIC_API_KEY

```
Repo → Settings → Secrets and variables → Actions → New repository secret
Nom    : ANTHROPIC_API_KEY
Valeur : sk-ant-api03-...
```

Sans ce secret, le rendu fonctionne mais les textes sont génériques.  
Avec ce secret, Claude Vision analyse chaque clip et génère hook + core + punchline cohérents.

### 4. Personal Access Token GitHub

```
GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens

Repository access : Only selected → ton repo App
Permissions :
  Repository permissions → Contents  : Read and write
  Repository permissions → Actions   : Read and write
  Repository permissions → Workflows : Read and write
```

Coller ce token dans App.html au démarrage.

---

## Utilisation

1. Ouvrir `App.html` dans un navigateur (Chrome ou Firefox)
2. Entrer le **token GitHub** + le nom du repo (`owner/repo`)
3. Onglet **Clips** → glisser 1 à 3 clips vidéo (MP4/MOV/AVI)
4. Réordonner par drag & drop si besoin, assigner les rôles (HOOK / CORE / PUNCH)
5. Onglet **Options** → configurer durées, effets, textes, format de sortie
6. Cliquer **Confirmer → Lancer le rendu**
7. Attendre ~60–120s → GitHub Actions → Artifacts → télécharger `output.mp4`

---

## Pipeline render.py — 7 étapes

```
[1/7] Extraction + analyse multi-métriques
      ffprobe → durée, dimensions, changements de scène
      audio RMS → niveau sonore moyen (proxy énergie)
      motion score → mouvement réel via diff de frames (PSNR)

[2/7] Classification narrative (scoring 3D)
      hook_score  = activité précoce × 12 + peak scdet + motion − durée
      core_score  = densité scènes × 8 + motion + durée
      punch_score = activité tardive × 12 + RMS audio − densité
      → ordre optimal : hook → core(s) → punchline

[3/7] Analyse IA visuelle (Claude Vision)
      3 frames par clip : début (10%), milieu (50%), fin (85%)
      → description contenu + émotion + thème par clip

[4/7] Génération textes narratifs (Claude)
      Contexte : descriptions visuelles + rôles narratifs
      → HOOK     : 4 mots max, MAJUSCULES, choc/WTF
      → CORE     : 5 mots, caption humoristique
      → PUNCHLINE: 6 mots, chute absurde + emoji
      Les 3 forment une micro-narration : tension → commentaire → chute

[5/7] Découpe + effets par segment
      → cut naturel au changement de scène le plus proche de la cible
      → zoom punch sur le core : pic choisi = max(score × proximité_milieu)
      → courbe ease-out sur le retour du zoom

[6/7] Assemblage
      → concat avec flash cut 1 frame blanche entre segments

[7/7] Textes animés (3 couches) + audio
      → Hook     : slide depuis le haut, blanc, bordure noire
      → Core text: fade in centré, blanc semi-transparent
      → Punchline: slide depuis le bas, jaune, bordure noire
      → merge audio avec fade out configurable
```

---

## Toutes les options

| Clé | Défaut | Description |
|-----|--------|-------------|
| `hook_dur` | `2.0` | Durée segment hook (s) |
| `core_dur` | `2.5` | Durée segment core (s) |
| `punch_dur` | `3.0` | Durée segment punchline (s) |
| `tolerance` | `0.7` | Fenêtre de recherche du cut naturel (±s) |
| `flash_cut` | `true` | Flash blanc 1 frame entre les segments |
| `zoom_punch` | `true` | Zoom punch sur le core |
| `zoom_scale` | `1.08` | Intensité du zoom (ex: 1.08 = +8%) |
| `ai_text` | `true` | Textes générés par Claude Vision |
| `auto_order` | `true` | Ordre des clips décidé par le scoring IA |
| `custom_hook` | `""` | Hook imposé (bypass IA) |
| `custom_punch` | `""` | Punchline imposée (bypass IA) |
| `resolution` | `720x1280` | Résolution sortie |
| `fps` | `24` | Images par seconde |
| `crf` | `18` | Qualité vidéo (15=max · 18=haut · 22=moyen · 28=web) |
| `audio_br` | `192` | Bitrate audio (kbps) |
| `fade_dur` | `0.3` | Durée fade out audio final (s) |
| `scdet_thr` | `10` | Seuil détection changements de scène |
| `hook_size` | `86` | Taille police hook (px) |
| `punch_size` | `62` | Taille police punchline (px) |
| `text_bg` | `false` | Fond semi-transparent sous les textes (réservé) |

---

## Format p.json

Structure envoyée par App.html lors de chaque rendu :

```json
{
  "videos": [
    { "data": "<base64 MP4>", "role": "hook" },
    { "data": "<base64 MP4>", "role": "core" },
    { "data": "<base64 MP4>", "role": "punch" }
  ],
  "options": {
    "hook_dur": 2.0,
    "core_dur": 2.5,
    "punch_dur": 3.0,
    "tolerance": 0.7,
    "flash_cut": true,
    "zoom_punch": true,
    "zoom_scale": 1.08,
    "ai_text": true,
    "auto_order": true,
    "custom_hook": "",
    "custom_punch": "",
    "resolution": "720x1280",
    "fps": 24,
    "crf": 18,
    "audio_br": 192,
    "fade_dur": 0.3,
    "scdet_thr": 10,
    "hook_size": 86,
    "punch_size": 62,
    "text_bg": false
  }
}
```

`role` peut être `"auto"`, `"hook"`, `"core"` ou `"punch"`.  
Si tous les rôles sont `"auto"` et `auto_order=true`, le scoring IA décide de l'ordre.

---

## Dépendances

| Composant | Source |
|-----------|--------|
| GitHub Actions | `ubuntu-latest` (fourni) |
| FFmpeg | `apt-get install ffmpeg` (automatique) |
| fonts-liberation | `apt-get install fonts-liberation` (automatique) |
| Python 3 | pré-installé sur ubuntu-latest |
| stdlib uniquement | `json, base64, os, subprocess, urllib, time` |
| Anthropic API | optionnel, via secret `ANTHROPIC_API_KEY` |

Aucune dépendance pip. Aucun `requirements.txt` nécessaire.

---

## Troubleshooting

**Le workflow ne se déclenche pas**  
→ Vérifier que le token a les droits `Actions: Read and write` et `Workflows: Read and write`

**Textes par défaut ("TAS VU CA")**  
→ Le secret `ANTHROPIC_API_KEY` est absent ou invalide dans le repo

**output.mp4 absent après le rendu**  
→ Vérifier les logs du step "Run render" dans GitHub Actions

**Vidéo en format letterbox (bandes noires)**  
→ Normal si les clips source sont en 4:3 ou 16:9 — le crop intelligent les recadre en 9:16

**Durée du rendu**  
→ Sans IA : ~30s · Avec IA Vision : ~60–90s · Avec clips lourds : jusqu'à 3–4 min
