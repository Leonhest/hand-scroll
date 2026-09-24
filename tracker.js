// Shared pinch-and-drag tracking logic used by both the visible panel and the
// headless offscreen document.

// Normalised hand travel across the whole frame → this many page pixels at 1×.
export const GAIN = 2500;
// Pinch = thumb-tip/index-tip distance relative to palm size. `settings.pinch`
// is the grab threshold; release happens at 1.5× that (hysteresis).
export const PINCH_RELEASE_FACTOR = 1.5;
// Consecutive frames the pinch must hold before it counts (rejects flickers).
export const PINCH_CONFIRM_FRAMES = 3;
// Minimum handedness score for a detection to be treated as a real hand.
export const MIN_HAND_SCORE = 0.8;

export const DEFAULT_SETTINGS = { sens: 1, invert: false, momentum: true, pinch: 0.22 };

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
// Fingertip distance includes depth so fingers that only overlap in 2D don't count.
const dist3 = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, (a.z - b.z) * 0.5);

// Batches fractional scroll deltas into integer messages to the service
// worker, never more than one in flight.
export function createScrollSender({ onError } = {}) {
  let pending = 0;
  let inFlight = false;

  async function flush() {
    if (inFlight) return;
    const dy = Math.round(pending);
    if (!dy) return;
    pending -= dy;
    inFlight = true;
    try {
      const res = await chrome.runtime.sendMessage({ type: 'scroll', dy });
      if (res && !res.ok && onError) onError(res.error);
    } catch {
      // service worker asleep or document closing; ignore
    } finally {
      inFlight = false;
      if (Math.abs(pending) >= 1) flush();
    }
  }

  return (px) => {
    if (Math.abs(px) < 0.25) return;
    pending += px;
    flush();
  };
}

// `settings` is read live so the caller can mutate it. `onState(state, lm)`
// receives 'idle' | 'tracking' | 'grab' plus the current hand landmarks.
export function createTracker({ settings, sendScroll, onState }) {
  let pinched = false;
  let smoothY = 0;
  let lastY = 0;
  let velocity = 0;
  let momentumActive = false;
  let lastTime = 0;
  let pinchFrames = 0;

  function release() {
    if (!pinched) return;
    pinched = false;
    momentumActive = settings.momentum && Math.abs(velocity) > 3;
  }

  // Momentum is stepped per camera frame, normalised to ~60fps decay.
  function stepMomentum(dtMs) {
    if (!momentumActive) return;
    velocity *= Math.pow(0.93, dtMs / 16.7);
    if (Math.abs(velocity) < 0.5) { momentumActive = false; return; }
    sendScroll(velocity * (dtMs / 16.7));
  }

  function frame(result, now = performance.now()) {
    const dt = lastTime ? Math.min(now - lastTime, 100) : 16.7;
    lastTime = now;

    let lm = result.landmarks && result.landmarks[0];
    const score = result.handedness?.[0]?.[0]?.score ?? 1;
    if (lm && score < MIN_HAND_SCORE) lm = null;
    if (!lm) {
      pinchFrames = 0;
      release();
      stepMomentum(dt);
      onState('idle', null);
      return;
    }

    const palm = dist(lm[0], lm[9]) || 1e-6;
    const ratio = dist3(lm[4], lm[8]) / palm;
    const y = (lm[4].y + lm[8].y) / 2;
    const onThreshold = settings.pinch;
    const offThreshold = settings.pinch * PINCH_RELEASE_FACTOR;

    if (!pinched) {
      pinchFrames = ratio < onThreshold ? pinchFrames + 1 : 0;
      if (pinchFrames >= PINCH_CONFIRM_FRAMES) {
        pinched = true;
        momentumActive = false;
        smoothY = y;
        lastY = y;
        velocity = 0;
      }
    } else if (ratio > offThreshold) {
      pinchFrames = 0;
      release();
    }

    if (pinched) {
      smoothY = smoothY * 0.4 + y * 0.6;
      const dyNorm = smoothY - lastY;
      lastY = smoothY;
      // Hand moves up (y decreases) → page is dragged up → scroll down (positive).
      let px = -dyNorm * GAIN * settings.sens;
      if (settings.invert) px = -px;
      velocity = velocity * 0.5 + px * 0.5;
      sendScroll(px);
      onState('grab', lm, ratio);
    } else {
      stepMomentum(dt);
      onState('tracking', lm, ratio);
    }
  }

  return { frame, get pinched() { return pinched; } };
}

export async function createHandLandmarker(vision, HandLandmarker) {
  const modelAssetPath = chrome.runtime.getURL('vendor/hand_landmarker.task');
  const opts = (delegate) => ({
    baseOptions: { modelAssetPath, delegate },
    runningMode: 'VIDEO',
    numHands: 1,
    minHandDetectionConfidence: 0.75,
    minHandPresenceConfidence: 0.75,
    minTrackingConfidence: 0.7,
  });
  try {
    return await HandLandmarker.createFromOptions(vision, opts('GPU'));
  } catch (e) {
    console.warn('GPU delegate failed, falling back to CPU', e);
    return await HandLandmarker.createFromOptions(vision, opts('CPU'));
  }
}

// Offscreen documents only have chrome.runtime, so settings come from the
// service worker and live updates arrive as 'settings-changed' broadcasts.
export async function loadSettings(settings) {
  const res = await chrome.runtime.sendMessage({ type: 'get-settings' });
  Object.assign(settings, DEFAULT_SETTINGS, (res && res.settings) || {});
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'settings-changed') Object.assign(settings, msg.settings || {});
  });
  return settings;
}

// Diagnostic log line, persisted by the service worker and shown in the panel.
export function log(source, msg) {
  console.log(`[${source}] ${msg}`);
  return chrome.runtime.sendMessage({ type: 'log', source, msg }).catch(() => {});
}
