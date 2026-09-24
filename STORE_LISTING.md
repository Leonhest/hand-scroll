# Chrome Web Store listing

Copy-paste source for the Developer Dashboard. Keep this in sync with the
published listing so resubmissions don't drift.

---

## Store listing tab

**Name** (45 max)
```
Hand Scroll
```

**Summary** (132 max)
```
Scroll web pages with a wave of your hand. Pinch your fingers to grab the page, move up or down. Runs entirely on your device.
```

**Category:** Accessibility
**Language:** English

**Description**
```
Scroll any web page without touching your mouse or keyboard. Pinch your thumb and
index finger together in front of your webcam to grab the page, then move your hand
up or down — exactly like dragging a touchscreen. Open your fingers to let go.

Useful when your hands are messy or busy: cooking from a recipe, following a repair
guide at the workbench, reading sheet music, working through a tutorial, or just
leaning back away from the desk.

EVERYTHING STAYS ON YOUR COMPUTER
Hand tracking runs locally in your browser using Google's MediaPipe Hands model,
which ships inside the extension. Camera frames are analysed and immediately
discarded — never recorded, never uploaded. The extension makes no network requests
at all and works with no internet connection. No accounts, no analytics, no tracking.

RUNS OUT OF SIGHT
Once it is on, there is no camera window cluttering your screen — tracking happens
invisibly in the background while you read. Click the toolbar icon to turn it on or
off; your camera indicator light shows you when it is active.

TUNE IT TO YOUR HAND
Right-click the toolbar icon for a camera preview with a live pinch readout, plus:
• Sensitivity — how far the page moves for a given hand movement
• Pinch strictness — how close your fingers must be to count as a pinch
• Invert direction — drag-the-page or scroll-wheel behaviour
• Momentum — flick to coast, like a phone

OPEN SOURCE
The full source is public at github.com/Leonhest/hand-scroll, so you can verify
every privacy claim by reading the code.

GOOD TO KNOW
• Needs a webcam and reasonable lighting.
• Chrome does not allow any extension to run on chrome:// pages, the Chrome Web
  Store, or the built-in PDF viewer, so scrolling does not work there. Ordinary
  websites are fine.
• Uses a little CPU while switched on, as any camera-based tracking does. Turn it
  off when you are not using it.
```

**Privacy policy URL**
```
https://leonhest.github.io/hand-scroll/privacy.html
```

**Homepage URL**
```
https://github.com/Leonhest/hand-scroll
```

**Support URL**
```
https://github.com/Leonhest/hand-scroll/issues
```

---

## Privacy tab

**Single purpose description**
```
Hand Scroll lets the user scroll the web page they are reading by making a hand
gesture in front of their webcam. That is its only function: detect a pinch gesture
and translate the hand's movement into scrolling on the active tab.
```

**Permission justifications**

`host permissions (<all_urls>)`
```
Scrolling a page requires running a short scroll instruction inside that page. The
extension exists to scroll whatever page the user is currently reading, which cannot
be predicted or limited to a fixed list of sites, so broad host access is required.
The injected code only scrolls the page — it reads no page content, no form data and
no browsing history, and nothing is transmitted anywhere.
```

`scripting`
```
Used to inject the small scroll function into the active tab when a hand gesture is
detected. This is the mechanism that actually moves the page.
```

`storage`
```
Stores the user's own settings (sensitivity, pinch strictness, invert direction,
momentum, on/off state) plus a short local diagnostic log shown in the extension's
troubleshooting panel. Local to the device; nothing is transmitted.
```

`offscreen`
```
Hand tracking needs a page context with camera and WebAssembly access. An offscreen
document lets that run without forcing the user to keep a visible camera window open
while they browse.
```

`contextMenus`
```
Adds one item, "Camera preview & settings", to the right-click menu of the
extension's own toolbar icon, which opens the preview and settings window.
```

**Remote code:** No, I am not using remote code.
The MediaPipe runtime (WebAssembly) and hand-landmark model are bundled in the
package under `vendor/` and loaded from the extension itself.

**Data usage:** No data collected. Certify all three compliance checkboxes.

---

## Graphic assets

| Asset | Size | Required |
| --- | --- | --- |
| Store icon | 128×128 | Yes — `icons/icon128.png` |
| Screenshot | 1280×800 | Yes, at least one (up to 5) |
| Small promo tile | 440×280 | Optional, but improves placement |
| Marquee promo tile | 1400×560 | Optional |
