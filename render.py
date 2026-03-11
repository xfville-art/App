name: VIRACUT

on:
  workflow_dispatch:

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  render:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install FFmpeg + fonts
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends ffmpeg fonts-liberation fontconfig
          fc-cache -f -v

      - name: Run render
        run: |
          # On s'assure que le script Python est lancé
          python3 render.py

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: viracut-output
          path: output.mp4  # Vérifie que ton render.py crée bien "output.mp4"
          if-no-files-found: error
