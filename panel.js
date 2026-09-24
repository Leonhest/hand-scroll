// Visible preview/settings window. Also the place where camera permission is
// granted the first time (the headless offscreen tracker can't prompt).
import { FilesetResolver, HandLandmarker } from './vendor/vision_bundle.mjs';
import { createTracker, createScrollSender, createHandLandmarker, loadSettings } from './tracker.js';

const app = document.getElementById('app');
const video = document.getElementById('video');
const canvas = document.getElementById('overlay');
const ctx = canvas.getContext('2d');
const badge = document.getElementById('badge');
const errorEl = document.getElementById('error');
const sensInput = document.getElementById('sens');
const sensVal = document.getElementById('sensVal');
const invertInput = document.getElementById('invert');
const momentumInput = document.getElementById('momentum');
const pinchInput = document.getElementById('pinch');
const pinchVal = document.getElementById('pinchVal');
const pipBtn = document.getElementById('pip');
const bgBtn = document.getElementById('background');
const logEl = document.getElementById('log');

async function renderLog() {
  const { log = [] } = await chrome.storage.local.get('log');
  logEl.textContent = log.join('\n') || '(empty)';
  logEl.scrollTop = logEl.scrollHeight;
}
renderLog();
chrome.storage.onChanged.addListener((c, area) => { if (area === 'local' && c.log) renderLog(); });
document.getElementById('clearLog').addEventListener('click', (e) => {
  e.preventDefault();
  chrome.runtime.sendMessage({ type: 'clear-log' });
});

const settings = {};
let landmarker = null;
let tracker = null;
let host = window;          // window whose requestAnimationFrame drives the loop
let rafHandle = 0;
let lastVideoTime = -1;
let pipWin = null;
let errorTimer = 0;

// ---------- settings ----------
function saveSettings() { chrome.storage.local.set({ settings }); }
sensInput.addEventListener('input', () => {
  settings.sens = parseFloat(sensInput.value);
  sensVal.textContent = settings.sens.toFixed(1);
  saveSettings();
});
pinchInput.addEventListener('input', () => {
  settings.pinch = parseFloat(pinchInput.value);
  pinchVal.textContent = settings.pinch.toFixed(2);
  saveSettings();
});
invertInput.addEventListener('change', () => { settings.invert = invertInput.checked; saveSettings(); });
momentumInput.addEventListener('change', () => { settings.momentum = momentumInput.checked; saveSettings(); });

// ---------- UI helpers ----------
const BADGE_TEXT = {
  idle: 'No hand in view',
  tracking: 'Hand found — pinch to grab',
  grab: 'Grabbing — move to scroll',
};
function setBadge(state, text = BADGE_TEXT[state]) {
  badge.className = `badge ${state}`;
  badge.textContent = text;
}
function showError(msg, autoHide = false) {
  errorEl.textContent = msg;
  errorEl.classList.remove('hidden');
  clearTimeout(errorTimer);
  if (autoHide) errorTimer = setTimeout(() => errorEl.classList.add('hidden'), 4000);
}

function drawOverlay(lm, pinched) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!lm) return;
  const w = canvas.width, h = canvas.height;
  const thumb = lm[4], index = lm[8];
  ctx.lineWidth = 3;
  ctx.strokeStyle = pinched ? '#06d6a0' : 'rgba(255,255,255,.6)';
  ctx.fillStyle = ctx.strokeStyle;
  ctx.beginPath();
  ctx.moveTo(thumb.x * w, thumb.y * h);
  ctx.lineTo(index.x * w, index.y * h);
  ctx.stroke();
  for (const p of [thumb, index]) {
    ctx.beginPath();
    ctx.arc(p.x * w, p.y * h, pinched ? 10 : 7, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ---------- frame loop ----------
function loop() {
  if (landmarker && video.readyState >= 2 && video.currentTime !== lastVideoTime) {
    lastVideoTime = video.currentTime;
    if (canvas.width !== video.videoWidth) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
    }
    try {
      tracker.frame(landmarker.detectForVideo(video, performance.now()));
    } catch (e) {
      console.error(e);
    }
  }
  rafHandle = host.requestAnimationFrame(loop);
}
function restartLoop() {
  for (const w of [window, pipWin]) { try { w && w.cancelAnimationFrame(rafHandle); } catch {} }
  rafHandle = host.requestAnimationFrame(loop);
}

// ---------- pop-out (Document Picture-in-Picture: always on top) ----------
if (!('documentPictureInPicture' in window)) {
  pipBtn.disabled = true;
  pipBtn.textContent = 'Pop out not supported in this Chrome';
}
pipBtn.addEventListener('click', async () => {
  try {
    pipWin = await documentPictureInPicture.requestWindow({ width: 340, height: 500 });
  } catch (e) {
    showError(`Pop out failed: ${e.message}`);
    return;
  }
  for (const link of document.querySelectorAll('link[rel="stylesheet"]')) {
    const l = pipWin.document.createElement('link');
    l.rel = 'stylesheet';
    l.href = link.href;
    pipWin.document.head.append(l);
  }
  pipWin.document.body.append(app);
  pipBtn.classList.add('hidden');
  const placeholder = document.createElement('p');
  placeholder.className = 'hint';
  placeholder.style.padding = '16px';
  placeholder.textContent = 'Hand Scroll is running in the pop-out window. Close that window to bring it back here.';
  document.body.append(placeholder);
  host = pipWin;
  restartLoop();
  pipWin.addEventListener('pagehide', () => {
    document.body.append(app);
    placeholder.remove();
    pipBtn.classList.remove('hidden');
    host = window;
    pipWin = null;
    restartLoop();
  });
});

// ---------- run in background ----------
bgBtn.addEventListener('click', async () => {
  bgBtn.disabled = true;
  bgBtn.textContent = 'Switching…';
  await chrome.runtime.sendMessage({ type: 'enable-background' }); // background closes this window
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden && host === window) {
    setBadge('idle', 'Window hidden — use Pop out or Run in background');
  }
});

// ---------- boot ----------
async function init() {
  await loadSettings(settings);
  sensInput.value = settings.sens;
  sensVal.textContent = settings.sens.toFixed(1);
  invertInput.checked = settings.invert;
  momentumInput.checked = settings.momentum;
  pinchInput.value = settings.pinch;
  pinchVal.textContent = settings.pinch.toFixed(2);

  const sendScroll = createScrollSender({
    onError: (err) => showError(`Couldn't scroll the page: ${err}\nSome pages (chrome://, the Web Store, PDFs) can't be scripted.`, true),
  });
  tracker = createTracker({
    settings,
    sendScroll,
    onState: (state, lm, ratio) => {
      drawOverlay(lm, tracker.pinched);
      // Show the live pinch value so the strictness slider can be tuned by eye.
      setBadge(state, ratio === undefined ? BADGE_TEXT[state] : `${BADGE_TEXT[state]}  ·  pinch ${ratio.toFixed(2)}`);
    },
  });

  setBadge('idle', 'Loading hand model…');
  const vision = await FilesetResolver.forVisionTasks(chrome.runtime.getURL('vendor/wasm'));
  landmarker = await createHandLandmarker(vision, HandLandmarker);

  setBadge('idle', 'Requesting camera…');
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
    audio: false,
  });
  video.srcObject = stream;
  await video.play();
  setBadge('idle');
  bgBtn.disabled = false;
  restartLoop();
}

init().catch((e) => {
  console.error(e);
  setBadge('idle', 'Error');
  showError(
    e.name === 'NotAllowedError'
      ? 'Camera access was denied. Click the camera icon in the address bar of this window to allow it, then reload.'
      : `Failed to start: ${e.message || e}`,
  );
});
