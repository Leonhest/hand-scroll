// Service worker: owns the on/off state, the headless offscreen tracker, the
// optional preview panel, and performs the actual scrolling in the active tab.

const PANEL_URL = chrome.runtime.getURL('panel.html');

async function log(msg, source = 'background') {
  const line = `${new Date().toLocaleTimeString()} [${source}] ${msg}`;
  console.log(line);
  try {
    const { log = [] } = await chrome.storage.local.get('log');
    log.push(line);
    await chrome.storage.local.set({ log: log.slice(-60) });
  } catch {}
}
const session = chrome.storage.session;

// ---------- state helpers (survive service-worker restarts) ----------
async function getEnabled() {
  return (await chrome.storage.local.get('enabled')).enabled === true;
}
async function setEnabled(v) {
  await chrome.storage.local.set({ enabled: v });
  await chrome.action.setBadgeText({ text: v ? 'ON' : '' });
  await chrome.action.setBadgeBackgroundColor({ color: '#06d6a0' });
  await chrome.action.setTitle({ title: v ? 'Hand Scroll: on (click to turn off)' : 'Hand Scroll: off (click to turn on)' });
}
async function getPanelWindowId() {
  return (await session.get('panelWindowId')).panelWindowId ?? null;
}

// ---------- active tab tracking ----------
const OWN_ORIGIN = chrome.runtime.getURL('');
const isScrollable = (tab) => tab && tab.url !== undefined && !tab.url.startsWith(OWN_ORIGIN);

async function rememberTab(tab) {
  if (isScrollable(tab)) await session.set({ lastTabId: tab.id });
}
async function rememberActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (isScrollable(tab)) { await rememberTab(tab); return tab.id; }
  // Fall back to the active tab of any normal window (e.g. the panel has focus).
  const tabs = await chrome.tabs.query({ active: true, windowType: 'normal' });
  const pick = tabs.find(isScrollable);
  if (pick) { await rememberTab(pick); return pick.id; }
  return null;
}
chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try { await rememberTab(await chrome.tabs.get(tabId)); } catch {}
});
chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  const [tab] = await chrome.tabs.query({ active: true, windowId });
  await rememberTab(tab);
});

// ---------- offscreen (headless) tracker ----------
async function offscreenExists() {
  const ctxs = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
  return ctxs.length > 0;
}
async function startOffscreen() {
  if ((await getPanelWindowId()) !== null) { await log('panel open, not starting offscreen'); return; }
  if (await offscreenExists()) { await log('offscreen already running'); return; }
  await log('creating offscreen tracker');
  try {
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Track hand gestures from the webcam to scroll the page',
    });
  } catch (e) {
    await log(`createDocument failed: ${e.message || e}`);
  }
}
async function stopOffscreen() {
  if (await offscreenExists()) await chrome.offscreen.closeDocument();
}

// ---------- preview panel ----------
async function openPanel() {
  await rememberActiveTab();
  const existing = await getPanelWindowId();
  if (existing !== null) {
    try {
      await chrome.windows.update(existing, { focused: true });
      return;
    } catch {
      await session.remove('panelWindowId');
    }
  }
  await stopOffscreen();
  const win = await chrome.windows.create({ url: PANEL_URL, type: 'popup', width: 380, height: 560 });
  await session.set({ panelWindowId: win.id });
}
async function closePanel() {
  const id = await getPanelWindowId();
  if (id !== null) {
    try { await chrome.windows.remove(id); } catch {}
    await session.remove('panelWindowId');
  }
}
chrome.windows.onRemoved.addListener(async (id) => {
  if (id === (await getPanelWindowId())) {
    await session.remove('panelWindowId');
    if (await getEnabled()) await startOffscreen();
  }
});

// ---------- toolbar button + context menu ----------
chrome.action.onClicked.addListener(async () => {
  const enabled = !(await getEnabled());
  await log(`toolbar click → ${enabled ? 'ON' : 'OFF'}`);
  await setEnabled(enabled);
  if (enabled) {
    await startOffscreen();
  } else {
    await stopOffscreen();
    await closePanel();
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: 'panel', title: 'Camera preview & settings', contexts: ['action'] });
});
chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId === 'panel') openPanel();
});

// Re-sync on every worker start (browser launch, worker restart).
(async () => {
  const enabled = await getEnabled();
  await setEnabled(enabled);
  if (enabled) await startOffscreen();
})();

// ---------- scrolling (runs inside the page) ----------
// Scrolls the document, or the largest scrollable container when the document
// itself doesn't move (web apps, chat UIs, ...).
function scrollPage(dy) {
  const canScroll = (el) => {
    if (!el) return false;
    const before = el.scrollTop;
    el.scrollBy({ top: dy, behavior: 'instant' });
    return el.scrollTop !== before;
  };

  const cached = window.__handScrollTarget;
  if (cached && cached.isConnected && canScroll(cached)) return;

  if (canScroll(document.scrollingElement)) {
    window.__handScrollTarget = document.scrollingElement;
    return;
  }

  let best = null;
  let bestArea = 0;
  for (const el of document.querySelectorAll('*')) {
    if (el.scrollHeight <= el.clientHeight + 1) continue;
    const style = getComputedStyle(el);
    if (!/(auto|scroll)/.test(style.overflowY)) continue;
    const rect = el.getBoundingClientRect();
    const area = rect.width * rect.height;
    if (area > bestArea && rect.width > 100 && rect.height > 100) {
      best = el;
      bestArea = area;
    }
  }
  if (best && canScroll(best)) window.__handScrollTarget = best;
}

async function doScroll(dy) {
  let { lastTabId } = await session.get('lastTabId');
  if (lastTabId != null) {
    try {
      if (!isScrollable(await chrome.tabs.get(lastTabId))) lastTabId = null;
    } catch {
      lastTabId = null; // tab was closed
    }
  }
  if (lastTabId == null) lastTabId = await rememberActiveTab();
  if (lastTabId == null) { await log('scroll: no target tab'); return { ok: false, error: 'no tab' }; }
  try {
    await chrome.scripting.executeScript({ target: { tabId: lastTabId }, func: scrollPage, args: [dy] });
    return { ok: true };
  } catch (e) {
    await log(`scroll failed on tab ${lastTabId}: ${e.message || e}`);
    return { ok: false, error: String(e.message || e) };
  }
}

// ---------- messages ----------
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.settings) {
    chrome.runtime.sendMessage({ type: 'settings-changed', settings: changes.settings.newValue || {} }).catch(() => {});
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  switch (msg.type) {
    case 'get-settings':
      chrome.storage.local.get('settings').then(({ settings }) => sendResponse({ settings: settings || {} }));
      return true;

    case 'log':
      log(msg.msg, msg.source);
      break;

    case 'scroll':
      doScroll(msg.dy).then(sendResponse);
      return true;

    case 'offscreen-status':
      log(`offscreen status: ${msg.status}${msg.state ? ' ' + msg.state : ''}${msg.error ? ' ' + msg.error : ''}`);
      if (msg.status === 'need-camera' || (msg.status === 'error' && msg.error === 'need-camera')) {
        // Camera permission must be granted from a visible page once.
        openPanel();
      } else if (msg.status === 'error') {
        console.error('offscreen error', msg.error);
      }
      break;

    case 'enable-background':
      // From the panel: turn on and hide the camera window.
      (async () => {
        await setEnabled(true);
        await closePanel(); // onRemoved → startOffscreen
        sendResponse({ ok: true });
      })();
      return true;

    case 'clear-log':
      chrome.storage.local.set({ log: [] }).then(() => sendResponse({ ok: true }));
      return true;

    case 'get-enabled':
      getEnabled().then((enabled) => sendResponse({ enabled }));
      return true;
  }
});
