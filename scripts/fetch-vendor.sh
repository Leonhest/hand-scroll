#!/usr/bin/env bash
# Re-downloads the vendored MediaPipe runtime and hand-landmark model into
# vendor/. These files are committed, so this is only needed to upgrade them.
set -euo pipefail
cd "$(dirname "$0")/.."

TASKS_VISION_VERSION="0.10.22-rc.20250304"
rm -rf vendor && mkdir -p vendor/wasm && cd vendor

curl -sL -o tasks-vision.tgz \
  "https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-${TASKS_VISION_VERSION}.tgz"
tar xzf tasks-vision.tgz
mv package/vision_bundle.mjs .
mv package/wasm/* wasm/
rm -rf package tasks-vision.tgz

curl -sL -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task

echo "vendor/ refreshed"
