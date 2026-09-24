#!/usr/bin/env bash
# Builds the Chrome Web Store upload package: hand-scroll-<version>.zip
# Only the files the extension actually loads go in — no repo scaffolding.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(python3 -c "import json;print(json.load(open('manifest.json'))['version'])")
OUT="hand-scroll-${VERSION}.zip"
rm -f "$OUT"

zip -r -q "$OUT" \
  manifest.json \
  background.js offscreen.html offscreen.js panel.html panel.css panel.js tracker.js \
  icons vendor \
  -x '*.DS_Store'

echo "$OUT  ($(du -h "$OUT" | cut -f1))"
unzip -l "$OUT" | tail -1
