// Headless tracker: runs in Chrome's invisible offscreen document. Frames are
// pulled from the camera via MediaStreamTrackProcessor, so nothing depends on
// requestAnimationFrame or timers (both are throttled in hidden documents).
import { FilesetResolver, HandLandmarker } from './vendor/vision_bundle.mjs';
import { createTracker, createScrollSender, createHandLandmarker, loadSettings, log } from './tracker.js';

const settings = {};
let lastState = null;
const L = (m) => log('offscreen', m);

function report(status, extra = {}) {
  chrome.runtime.sendMessage({ type: 'offscreen-status', status, ...extra }).catch(() => {});
}

async function main() {
  L('starting');
  await loadSettings(settings);

  const perm = await navigator.permissions.query({ name: 'camera' });
  L(`camera permission: ${perm.state}`);
  if (perm.state !== 'granted') {
    report('need-camera');
    return;
  }

  const vision = await FilesetResolver.forVisionTasks(chrome.runtime.getURL('vendor/wasm'));
  const landmarker = await createHandLandmarker(vision, HandLandmarker);
  L('hand model loaded');

  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
    audio: false,
  });
  const [track] = stream.getVideoTracks();
  const s = track.getSettings();
  L(`camera open ${s.width}x${s.height} @${s.frameRate}fps`);

  if (typeof MediaStreamTrackProcessor === 'undefined') {
    throw new Error('MediaStreamTrackProcessor not available in this Chrome');
  }

  let scrollErr = null;
  const sendScroll = createScrollSender({
    onError: (err) => { if (err !== scrollErr) { scrollErr = err; L(`scroll failed: ${err}`); } },
  });
  const tracker = createTracker({
    settings,
    sendScroll,
    onState: (state) => {
      if (state !== lastState) {
        lastState = state;
        L(`state: ${state}`);
        report('running', { state });
      }
    },
  });

  report('running', { state: 'idle' });

  const reader = new MediaStreamTrackProcessor({ track }).readable.getReader();
  let frames = 0;
  for (;;) {
    const { value: frame, done } = await reader.read();
    if (done) break;
    try {
      const bitmap = await createImageBitmap(frame);
      try {
        tracker.frame(landmarker.detectForVideo(bitmap, performance.now()));
      } finally {
        bitmap.close();
      }
      frames++;
      if (frames === 1) L('first frame processed');
      if (frames === 300) L('300 frames processed, tracking loop healthy');
    } catch (e) {
      L(`frame error: ${e.message || e}`);
    } finally {
      frame.close();
    }
  }
  L('camera stream ended');
  report('stopped');
}

main().catch((e) => {
  L(`FATAL: ${e.name}: ${e.message || e}`);
  report('error', { error: e.name === 'NotAllowedError' ? 'need-camera' : String(e.message || e) });
});
