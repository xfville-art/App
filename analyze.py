"""
analyze.py — ViraCut Studio v10  ★ LesCrados.Ai Edition ★
  Gemini 1.5 Flash (gratuit) — aistudio.google.com
══════════════════════════════════════════════════════════
Analyse de viralité PRÉ-RENDU via Claude API.
Lit pa.json (métadonnées clips, config actuelle).
Retourne un JSON entre markers avec :
  - score global 0-100
  - 5 axes détaillés
  - recommandations
  - recommended_config : mode, durées, effets, ordre clips
"""
import json, os, sys, urllib.request, urllib.error

MARKER_START = "##VIRALITE_JSON_START##"
MARKER_END   = "##VIRALITE_JSON_END##"


def extract_json(text):
    """Extrait le premier objet JSON valide depuis une réponse LLM."""
    text = text.strip()
    # Supprimer les blocs markdown ```json ... ```
    import re
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()
    # Chercher le premier { ... } complet
    start = text.find('{')
    if start == -1:
        raise ValueError("Aucun JSON trouvé dans la réponse")
    depth = 0
    for i, c in enumerate(text[start:], start):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i+1])
    raise ValueError("JSON incomplet dans la réponse")


def call_llm(api_key, prompt):
    """
    GitHub Models — gratuit, zéro blocage (même réseau que Actions).
    GITHUB_TOKEN automatiquement disponible dans tout workflow Actions.
    Endpoint : https://models.inference.ai.azure.com
    """
    models = [
        "meta-llama-3.3-70b-instruct",
        "gpt-4o-mini",
        "mistral-nemo",
        "meta-llama-3.1-8b-instruct",
    ]
    last_err = None
    for model in models:
        req = urllib.request.Request(
            "https://models.inference.ai.azure.com/chat/completions",
            data = json.dumps({
                "model":       model,
                "messages":    [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens":  1200,
            }).encode(),
            headers = {
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method = "POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode())
            text = body["choices"][0]["message"]["content"]
            print(f"  Modèle utilisé : {model}")
            return text
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:200]
            print(f"  {model} → HTTP {e.code} — essai suivant")
            last_err = Exception(f"HTTP {e.code}: {err_body}")
        except Exception as e:
            print(f"  {model} → {e} — essai suivant")
            last_err = e

    raise last_err or Exception("Tous les modèles GitHub ont échoué")


def main():
    # ── Lecture pa.json ──────────────────────────────────────────────
    # Cherche pa.json (analyze-only) ou p.json (rendu complet) en fallback
    if os.path.exists("pa.json"):
        payload_file = "pa.json"
    elif os.path.exists("p.json"):
        payload_file = "p.json"
        print("  (pa.json absent — fallback sur p.json)")
    else:
        print("ERREUR : ni pa.json ni p.json trouvés")
        sys.exit(1)

    with open(payload_file) as f:
        data = json.load(f)

    # Supporte les deux formats : pa.json (clips_meta) et p.json (videos avec data base64)
    if "clips_meta" in data:
        clips_meta = data.get("clips_meta", [])
    else:
        # Extraire métadonnées depuis p.json (videos array)
        clips_meta = []
        for i, v in enumerate(data.get("videos", [])):
            raw_bytes = len(v.get("data","")) * 3 // 4  # approx base64 decode size
            clips_meta.append({
                "index":   i + 1,
                "role":    v.get("role", "auto"),
                "size_mb": round(raw_bytes / 1_048_576, 2),
                "name":    f"clip_{i+1}.mp4",
            })

    current_mode = data.get("current_mode", data.get("options", {}).get("mode", "auto"))
    opts         = data.get("options", {})

    api_key = os.environ.get("GITHUB_TOKEN", "")
    if not api_key:
        print("ERREUR : GITHUB_TOKEN absent (ne devrait jamais arriver dans un workflow Actions)")
        sys.exit(1)

    print("=" * 60)
    print("  ViraCut Analyze v10 — LesCrados.Ai")
    print("=" * 60)
    print(f"  Clips         : {len(clips_meta)}")
    print(f"  Mode actuel   : {current_mode.upper()}")

    # ── Prompt Claude ────────────────────────────────────────────────
    clips_desc = "\n".join(
        f"  Clip {c['index']} — rôle={c['role']} taille={c['size_mb']}MB nom={c['name']}"
        for c in clips_meta
    )

    prompt = f"""Tu es un expert TikTok spécialisé dans Les Crados (cartes satiriques absurdes style Garbage Pail Kids, public français, format 9:16).

Analyse ces clips AVANT montage et optimise la config pour maximiser la rétention TikTok.

CLIPS ({len(clips_meta)}) :
{clips_desc}

CONFIG ACTUELLE :
- Mode : {current_mode.upper()}
- Hook dur : {opts.get('hook_dur', 2)}s
- Core dur : {opts.get('core_dur', 2.5)}s
- Punch dur : {opts.get('punch_dur', 3)}s
- Flash cut : {opts.get('flash_cut', True)}
- Zoom punch : {opts.get('zoom_punch', True)}
- Textes IA : {opts.get('ai_text', True)}
- Résolution : {opts.get('resolution', '720x1280')}

RÈGLES Les Crados TikTok :
- Durée idéale : 7-9s pour PUNCH, 20-26s pour CINÉMA
- Hook doit accrocher en 1.5-2s max (image choc, texte percutant)
- Le clip le plus visuellement fort = hook
- Punchline = dernier clip, doit être absurde/choquant
- Loop parfait = fin qui rappelle le début
- Flash cut + zoom punch = essentiels pour le PUNCH
- Si 1 seul clip : mode CINÉMA obligatoire

Réponds UNIQUEMENT en JSON valide, zéro texte avant ou après :
{{
  "score": <entier 0-100>,
  "axes": [
    {{"name": "Structure", "score": <0-100>}},
    {{"name": "Rythme",    "score": <0-100>}},
    {{"name": "Loop",      "score": <0-100>}},
    {{"name": "Diversité", "score": <0-100>}},
    {{"name": "Format",    "score": <0-100>}}
  ],
  "recs": [
    {{"type": "pos", "text": "<point fort concis max 60 chars>"}},
    {{"type": "neg", "text": "<point faible concis max 60 chars>"}},
    {{"type": "tip", "text": "<conseil actionnable max 60 chars>"}}
  ],
  "recommended_config": {{
    "mode": "<auto|punch|cinema>",
    "hook_dur": <float>,
    "core_dur": <float>,
    "punch_dur": <float>,
    "flash_cut": <bool>,
    "zoom_punch": <bool>,
    "ai_text": <bool>,
    "clip_order": [<indices 0-based dans le meilleur ordre hook→core→punch>]
  }}
}}"""

    # ── Appel API ────────────────────────────────────────────────────
    print("\n  Appel Claude API…")
    try:
        raw = call_llm(api_key, prompt)
        result = extract_json(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERREUR Gemini API HTTP {e.code} : {body[:500]}")
        sys.exit(1)
    except Exception as e:
        print(f"ERREUR : {e}")
        sys.exit(1)

    # ── Affichage résultat ───────────────────────────────────────────
    print(f"\n  Score viralité : {result.get('score', '?')}/100")
    for ax in result.get("axes", []):
        print(f"    {ax['name']:12s}: {ax['score']}")
    rc = result.get("recommended_config", {})
    print(f"\n  Config recommandée :")
    print(f"    Mode       : {rc.get('mode','?').upper()}")
    print(f"    Hook/Core/Punch : {rc.get('hook_dur','?')}s / {rc.get('core_dur','?')}s / {rc.get('punch_dur','?')}s")
    print(f"    Ordre clips : {rc.get('clip_order','?')}")
    print(f"    Flash={rc.get('flash_cut','?')}  Zoom={rc.get('zoom_punch','?')}  Textes={rc.get('ai_text','?')}")
    for r in result.get("recs", []):
        icon = "✓" if r['type']=='pos' else ("✗" if r['type']=='neg' else "→")
        print(f"    {icon} {r['text']}")

    # ── Markers pour parsing App.html ────────────────────────────────
    print(f"\n{MARKER_START}")
    print(json.dumps(result, ensure_ascii=False))
    print(f"{MARKER_END}")
    print("\n  Analyse terminée.")


if __name__ == "__main__":
    main()
