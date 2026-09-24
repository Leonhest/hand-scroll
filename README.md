# Hand Scroll

A Chrome extension that scrolls web pages with a webcam hand gesture: **pinch your
thumb and index finger together to grab the page, then move your hand up or down**,
like dragging a touchscreen. Release to let go.

All hand tracking runs locally in the browser via [MediaPipe Hands](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker).
No video ever leaves the machine, and the extension makes no network requests.

## Install

Load it unpacked:

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right)
3. **Load unpacked** → select this folder
4. Click the Hand Scroll toolbar icon to toggle tracking **ON**
5. Allow camera access the first time (a preview window opens for the prompt)

## Use

- **Toolbar icon** — toggles tracking on/off. When ON, tracking runs invisibly in
  the background; the only visible sign is the camera indicator light.
- **Right-click the icon → Camera preview & settings** — shows the camera feed with
  a live pinch readout, plus the settings below and a diagnostics log.
- **Pop out (always on top)** — floats the preview over other windows.
- **Run in background (hide camera)** — closes the preview, keeps tracking.

### Settings

| Setting | What it does |
| --- | --- |
| Sensitivity | How much page scroll a given hand movement produces |
| Pinch strictness | How close the fingers must be to count as a pinch (lower = stricter) |
| Invert direction | Swaps drag-the-page for scroll-wheel behaviour |
| Momentum | Flick-to-coast after releasing a fast drag |

Settings apply live to the background tracker.

## How it works

| File | Role |
| --- | --- |
| `tracker.js` | Shared gesture logic — pinch detection, smoothing, momentum |
| `offscreen.js` | Headless tracker in an offscreen document (the normal ON path) |
| `panel.js` | Visible preview window: camera feed, settings, diagnostics |
| `background.js` | Service worker: on/off state, tab targeting, performs the scroll |

Two details worth knowing:

- A hidden page gets no `requestAnimationFrame` and throttled timers, which would
  stall tracking. The offscreen tracker therefore pulls frames directly from the
  camera with `MediaStreamTrackProcessor`, so the camera paces the loop.
- Offscreen documents have no `chrome.storage` access, so settings and log lines
  are relayed through the service worker.

Pinch tuning constants live at the top of `tracker.js`.

## Limitations

Chrome forbids extensions from scripting `chrome://` pages, the Chrome Web Store,
and the built-in PDF viewer, so scrolling does not work there. Ordinary websites
are fine.

## Publishing

`scripts/package.sh` builds the Chrome Web Store upload zip from just the runtime
files. Listing copy, permission justifications, and asset requirements live in
[`STORE_LISTING.md`](STORE_LISTING.md); the privacy policy the listing points at is
[`docs/privacy.html`](docs/privacy.html), served at
<https://leonhest.github.io/hand-scroll/privacy.html>.

## Vendored files

`vendor/` holds the MediaPipe runtime and hand-landmark model (~26 MB), committed so
the extension loads unpacked with no build step. Manifest V3 forbids remotely-hosted
code, so these must be bundled. Refresh them with `scripts/fetch-vendor.sh`.
