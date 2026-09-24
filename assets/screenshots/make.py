#!/usr/bin/env python3
"""Generates the Chrome Web Store screenshots (1280x800) as SVG, then PNG via
rsvg-convert. Hands are Blender renders from hands/render_hands.py; re-run
that first after changing a pose. Run from anywhere:
python3 assets/screenshots/make.py"""
import base64
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1280, 800
FONT = 'font-family="Helvetica Neue, Helvetica, Arial, sans-serif"'
MINT = "#6ae7c2"
GREEN = "#06d6a0"
with open(os.path.join(HERE, "..", "..", "icons", "icon48.png"), "rb") as _f:
    ICON_URI = "data:image/png;base64," + base64.b64encode(_f.read()).decode()

def _load_hand(pose):
    with open(os.path.join(HERE, "hands", f"{pose}.png"), "rb") as f:
        uri = "data:image/png;base64," + base64.b64encode(f.read()).decode()
    with open(os.path.join(HERE, "hands", f"{pose}.json")) as f:
        meta = json.load(f)
    return uri, meta


HANDS = {pose: _load_hand(pose) for pose in ("open", "pinch")}

# Fades the forearm out toward the bottom of each hand render.
HAND_DEFS = """
  <linearGradient id="fadeGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset=".62" stop-color="#fff"/><stop offset=".86" stop-color="#000"/>
  </linearGradient>
  <mask id="fade" maskContentUnits="objectBoundingBox"><rect width="1" height="1" fill="url(#fadeGrad)"/></mask>"""


def hand(pose, x, y, s=1.0, opacity=1.0, dots=True):
    """Illustrated hand render at (x, y) scaled by s, with the thumb/index
    tracking overlay the real preview draws (green when pinched)."""
    uri, meta = HANDS[pose]
    w, h = meta["w"] * s, meta["h"] * s
    out = [f'<g opacity="{opacity}">',
           f'<image x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" href="{uri}" mask="url(#fade)"/>']
    if dots:
        (tx, ty), (ix, iy) = [(x + px * s, y + py * s) for px, py in (meta["points"][4], meta["points"][8])]
        if pose == "pinch":
            cx, cy = (tx + ix) / 2, (ty + iy) / 2
            # a ring, so the touching fingertips stay visible inside it
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{17*s:.1f}" fill="{GREEN}" fill-opacity=".12" '
                       f'stroke="{GREEN}" stroke-width="{3*s:.1f}"/>')
        else:
            out.append(f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{ix:.1f}" y2="{iy:.1f}" stroke="#fff" stroke-opacity=".75" '
                       f'stroke-width="{3*s:.1f}" stroke-dasharray="{6*s:.1f} {6*s:.1f}" stroke-linecap="round"/>')
            for px, py in ((tx, ty), (ix, iy)):
                out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{7.5*s:.1f}" fill="#fff" stroke="{MINT}" stroke-width="{2.5*s:.1f}"/>')
    out.append('</g>')
    return "\n".join(out)


def background(extra=""):
    return f'''<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#17664d"/><stop offset="1" stop-color="#082b20"/>
  </linearGradient>{HAND_DEFS}{extra}
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>'''


def title(main, sub):
    return (f'<text {FONT} x="640" y="112" text-anchor="middle" fill="#fff" font-size="54" font-weight="700">{main}</text>'
            f'<text {FONT} x="640" y="158" text-anchor="middle" fill="#9fdcc7" font-size="24">{sub}</text>')


def pill(x, y, w, text, fill, color):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="17" fill="{fill}"/>'
            f'<text {FONT} x="{x + w/2}" y="{y + 23}" text-anchor="middle" fill="{color}" font-size="15" font-weight="700">{text}</text>')


def mini_page(x, y, w, h, scroll=0):
    """Stylised web page; `scroll` shifts the content up and the thumb down."""
    lines = []
    cy = 40 - scroll
    rows = [("t", 0.6), ("l", .92), ("l", .84), ("l", .88), ("img", 1), ("l", .9), ("l", .8),
            ("t", .5), ("l", .93), ("l", .86), ("l", .9), ("l", .7), ("img", 1), ("l", .88), ("l", .82)]
    for kind, frac in rows:
        hh = {"t": 11, "l": 7, "img": 58}[kind]
        gap = {"t": 16, "l": 11, "img": 16}[kind]
        if 30 < cy and cy + hh < h - 8:
            fill = {"t": "#8fa39c", "l": "#c4ceca", "img": "#d4ddd9"}[kind]
            lines.append(f'<rect x="{x+16}" y="{y+cy}" width="{(w-40)*frac:.0f}" height="{hh}" rx="{min(hh/2,6)}" fill="{fill}"/>')
        cy += hh + gap
    thumb_y = y + 36 + min(scroll * 0.5, h - 110)
    return f'''<g>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#f4f6f5"/>
  <path d="M{x} {y+12} a12 12 0 0 1 12 -12 h{w-24} a12 12 0 0 1 12 12 v14 h-{w} z" fill="#dfe5e2"/>
  <circle cx="{x+15}" cy="{y+13}" r="4" fill="#f26b5b"/><circle cx="{x+29}" cy="{y+13}" r="4" fill="#f5bf4f"/><circle cx="{x+43}" cy="{y+13}" r="4" fill="#5dc766"/>
  {"".join(lines)}
  <rect x="{x+w-9}" y="{y+34}" width="4" height="{h-44}" rx="2" fill="#dfe5e2"/>
  <rect x="{x+w-9}" y="{thumb_y:.0f}" width="4" height="56" rx="2" fill="#8fa39c"/>
</g>'''


def card(x, y, n, highlight=False):
    stroke = f'stroke="{MINT}" stroke-opacity=".55" stroke-width="2"' if highlight else 'stroke="#fff" stroke-opacity=".12"'
    return (f'<rect x="{x}" y="{y}" width="340" height="450" rx="22" fill="#fff" fill-opacity=".06" {stroke}/>'
            f'<text {FONT} x="{x+28}" y="{y+50}" fill="{MINT}" font-size="20" font-weight="700">{n}</text>')


def caption(x, y, text):
    return f'<text {FONT} x="{x+170}" y="{y+425}" text-anchor="middle" fill="#fff" font-size="21" font-weight="600">{text}</text>'


# ---------------------------------------------------------------- screenshot 1
def shot_gesture():
    cy = 214
    parts = [background(), title("Pinch to grab. Move to scroll.", "Like dragging a touchscreen — without touching anything.")]

    x = 90
    hs = 1.2
    hx = (340 - HANDS["open"][1]["w"] * hs) / 2
    parts += [card(x, cy, 1), hand("open", x + hx, cy - 34, hs), pill(x + 70, cy + 350, 200, "Hand found", "#00000059", "#ffd166"),
              caption(x, cy, "Show your hand")]
    x = 470
    parts += [card(x, cy, 2, True), hand("pinch", x + hx, cy - 34, hs), pill(x + 70, cy + 350, 200, "Grabbing", GREEN, "#012"),
              caption(x, cy, "Pinch to grab the page")]
    x = 850
    parts += [card(x, cy, 3),
              hand("pinch", x - 34, cy + 6, .8),
              f'<g stroke="{MINT}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none">'
              f'<path d="M{x+150} {cy+300} L{x+150} {cy+100}"/><path d="M{x+140} {cy+114} L{x+150} {cy+98} L{x+160} {cy+114}"/></g>',
              mini_page(x + 172, cy + 74, 144, 250, scroll=70),
              pill(x + 70, cy + 350, 200, "Scrolling", GREEN, "#012"), caption(x, cy, "Move your hand to scroll")]
    parts.append(f'<text {FONT} x="640" y="730" text-anchor="middle" fill="#63b79b" font-size="19">Open your fingers to let go — flick for momentum.</text>')
    return parts


# ---------------------------------------------------------------- screenshot 2
def shot_background():
    parts = [background('''
  <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
    <feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#000" flood-opacity=".45"/>
  </filter>'''),
             title("No camera window. Just scroll.", "Tracking runs invisibly in the background while you read.")]
    bx, by, bw, bh = 150, 210, 980, 540
    parts.append(f'<g filter="url(#shadow)"><rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="14" fill="#fbfcfb"/></g>')
    # browser chrome: tab strip + toolbar
    parts.append(f'''
<path d="M{bx} {by+14} a14 14 0 0 1 14 -14 h{bw-28} a14 14 0 0 1 14 14 v76 h-{bw} z" fill="#e6ebe8"/>
<circle cx="{bx+22}" cy="{by+22}" r="6" fill="#f26b5b"/><circle cx="{bx+42}" cy="{by+22}" r="6" fill="#f5bf4f"/><circle cx="{bx+62}" cy="{by+22}" r="6" fill="#5dc766"/>
<path d="M{bx+90} {by+44} v-20 a8 8 0 0 1 8 -8 h204 a8 8 0 0 1 8 8 v20 z" fill="#fbfcfb"/>
<text {FONT} x="{bx+110}" y="{by+36}" fill="#334" font-size="14">Weeknight lasagne — Recipe</text>
<rect x="{bx}" y="{by+44}" width="{bw}" height="46" fill="#fbfcfb"/>
<rect x="{bx+100}" y="{by+53}" width="{bw-260}" height="30" rx="15" fill="#eef1ef"/>
<text {FONT} x="{bx+122}" y="{by+73}" fill="#667" font-size="14">example-recipes.com/weeknight-lasagne</text>
<line x1="{bx}" y1="{by+90}" x2="{bx+bw}" y2="{by+90}" stroke="#e1e6e3"/>''')
    # toolbar extension icon with ON badge
    ix, iy = bx + bw - 118, by + 54
    parts.append(f'''
<rect x="{ix-6}" y="{iy-4}" width="40" height="36" rx="10" fill="{MINT}" fill-opacity=".25"/>
<image x="{ix}" y="{iy}" width="28" height="28" href="{ICON_URI}"/>
<rect x="{ix+14}" y="{iy+17}" width="26" height="15" rx="4" fill="{GREEN}"/>
<text {FONT} x="{ix+27}" y="{iy+28.5}" text-anchor="middle" fill="#012" font-size="10" font-weight="800">ON</text>
<circle cx="{bx+bw-58}" cy="{iy+14}" r="11" fill="#dfe5e2"/>
<g fill="#8a9690"><circle cx="{bx+bw-26}" cy="{iy+7}" r="2.4"/><circle cx="{bx+bw-26}" cy="{iy+14}" r="2.4"/><circle cx="{bx+bw-26}" cy="{iy+21}" r="2.4"/></g>''')
    # page content: a recipe
    px, py = bx + 90, by + 130
    parts.append(f'''
<text {FONT} x="{px}" y="{py}" fill="#1c2b26" font-size="34" font-weight="700">Weeknight lasagne</text>
<text {FONT} x="{px}" y="{py+32}" fill="#6b7a74" font-size="16">Serves 4 · 45 minutes</text>
<clipPath id="dish"><rect x="{px}" y="{py+58}" width="330" height="200" rx="12"/></clipPath>
<g clip-path="url(#dish)">
  <rect x="{px}" y="{py+58}" width="330" height="200" fill="#f1e7da"/>
  <rect x="{px+40}" y="{py+92}" width="250" height="138" rx="8" fill="#ffffff"/>
  <g transform="translate({px+75},{py+104})">
    <path d="M0 18 Q 90 -4 180 18 V 26 H 0 Z" fill="#e8a33d"/>
    <rect y="26" width="180" height="14" fill="#f4e2b8"/>
    <rect y="40" width="180" height="16" fill="#b8452e"/>
    <rect y="56" width="180" height="11" fill="#f4e2b8"/>
    <rect y="67" width="180" height="16" fill="#c2533a"/>
    <rect y="83" width="180" height="11" fill="#f4e2b8"/>
    <rect y="94" width="180" height="12" fill="#a83f2a"/>
  </g>
  <g fill="#5f9e4a"><circle cx="{px+120}" cy="{py+118}" r="5"/><circle cx="{px+180}" cy="{py+112}" r="4"/><circle cx="{px+225}" cy="{py+119}" r="4.5"/></g>
</g>
<text {FONT} x="{px+380}" y="{py+96}" fill="#1c2b26" font-size="20" font-weight="700">Method</text>''')
    steps = ["Brown the mince with onion and garlic.", "Stir in tomatoes; simmer 15 min.",
             "Layer sauce, pasta sheets and béchamel.", "Top with cheese. Bake 25 min at 190°C.",
             "Rest 5 minutes before slicing."]
    for i, st in enumerate(steps):
        yy = py + 134 + i * 34
        parts.append(f'<circle cx="{px+392}" cy="{yy-6}" r="12" fill="#e6f3ee"/>'
                     f'<text {FONT} x="{px+392}" y="{yy-1}" text-anchor="middle" fill="#1f7a5e" font-size="13" font-weight="700">{i+1}</text>'
                     f'<text {FONT} x="{px+414}" y="{yy}" fill="#3b4a45" font-size="17">{st}</text>')
    # callout under the icon
    cw, ch = 300, 84
    cx0, cy0 = ix + 14 - cw + 40, iy + 50
    parts.append(f'''
<g>
  <path d="M{ix+6} {cy0} L{ix+14} {cy0-10} L{ix+22} {cy0} Z" fill="#0d3a2c"/>
  <rect x="{cx0}" y="{cy0}" width="{cw}" height="{ch}" rx="14" fill="#0d3a2c"/>
  <text {FONT} x="{cx0+20}" y="{cy0+34}" fill="#fff" font-size="19" font-weight="700">Click to turn on or off</text>
  <text {FONT} x="{cx0+20}" y="{cy0+60}" fill="#9fdcc7" font-size="15">Your camera light shows when it's on.</text>
</g>''')
    # hands-busy hint
    parts.append(f'''
<g transform="translate({px+380},{py+320})">
  <rect width="420" height="60" rx="12" fill="#eef7f3" stroke="#cfe9df"/>
  <text {FONT} x="20" y="37" fill="#1f7a5e" font-size="17" font-weight="600">Messy hands? Pinch the air to scroll the recipe.</text>
</g>''')
    return parts


# ---------------------------------------------------------------- screenshot 3
def shot_settings():
    parts = [background('''
  <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
    <feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#000" flood-opacity=".45"/>
  </filter>''')]
    # left copy
    parts.append(f'''
<text {FONT} x="110" y="250" fill="#fff" font-size="50" font-weight="700">Tune it to</text>
<text {FONT} x="110" y="310" fill="#fff" font-size="50" font-weight="700">your hand.</text>
<text {FONT} x="110" y="366" fill="#9fdcc7" font-size="22">Right-click the toolbar icon for a live</text>
<text {FONT} x="110" y="396" fill="#9fdcc7" font-size="22">preview and settings.</text>''')
    feats = [("Pinch strictness", "How close your fingers must be"), ("Sensitivity", "How far the page moves"),
             ("Momentum", "Flick to coast, like a phone"), ("Runs on-device", "No video ever leaves your computer")]
    for i, (a, b) in enumerate(feats):
        yy = 468 + i * 62
        parts.append(f'<circle cx="122" cy="{yy-6}" r="11" fill="{MINT}" fill-opacity=".2"/>'
                     f'<path d="M116 {yy-6} l4 4 l8 -8" stroke="{MINT}" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                     f'<text {FONT} x="146" y="{yy}" fill="#fff" font-size="19" font-weight="700">{a}</text>'
                     f'<text {FONT} x="146" y="{yy+24}" fill="#8cc9b4" font-size="16">{b}</text>')
    # panel window (mirrors panel.html / panel.css)
    wx, ww, wh = 700, 460, 628
    wy = (H - wh) // 2
    parts.append(f'<g filter="url(#shadow)"><rect x="{wx}" y="{wy}" width="{ww}" height="{wh}" rx="14" fill="#111"/></g>')
    parts.append(f'''
<path d="M{wx} {wy+14} a14 14 0 0 1 14 -14 h{ww-28} a14 14 0 0 1 14 14 v20 h-{ww} z" fill="#262626"/>
<circle cx="{wx+20}" cy="{wy+17}" r="6" fill="#f26b5b"/><circle cx="{wx+40}" cy="{wy+17}" r="6" fill="#f5bf4f"/><circle cx="{wx+60}" cy="{wy+17}" r="6" fill="#5dc766"/>
<text {FONT} x="{wx+ww/2}" y="{wy+22}" text-anchor="middle" fill="#bbb" font-size="13" font-weight="600">Hand Scroll</text>''')
    sx, sy, sw, sh = wx + 14, wy + 48, ww - 28, (ww - 28) * 3 / 4
    parts.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh:.0f}" rx="10" fill="#000"/>')
    parts.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh:.0f}" rx="10" fill="{MINT}" fill-opacity=".04"/>')
    ps = 1.25
    parts.append(f'<clipPath id="cam"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh:.0f}" rx="10"/></clipPath>'
                 f'<g clip-path="url(#cam)">'
                 + hand("pinch", sx + (sw - HANDS["pinch"][1]["w"] * ps) / 2, sy - 30, ps) + '</g>')
    parts.append(f'<rect x="{sx+12}" y="{sy+12}" width="292" height="28" rx="14" fill="{GREEN}"/>'
                 f'<text {FONT} x="{sx+26}" y="{sy+31}" fill="#012" font-size="13" font-weight="700">Grabbing — move to scroll  ·  pinch 0.14</text>')
    y = sy + sh + 30

    def slider(label, value, frac, hint=""):
        nonlocal y
        out = (f'<text {FONT} x="{sx}" y="{y}" fill="#eee" font-size="14">{label} <tspan fill="#fff" font-weight="700">{value}</tspan>'
               f'<tspan fill="#888" dx="6">{hint}</tspan></text>'
               f'<rect x="{sx}" y="{y+12}" width="{sw}" height="5" rx="2.5" fill="#3a3a3a"/>'
               f'<rect x="{sx}" y="{y+12}" width="{sw*frac:.0f}" height="5" rx="2.5" fill="#8ab4f8"/>'
               f'<circle cx="{sx+sw*frac:.0f}" cy="{y+14.5}" r="8" fill="#8ab4f8"/>')
        y += 52
        return out

    parts.append(slider("Sensitivity", "1.2×", .33))
    parts.append(slider("Pinch strictness", "0.22", .4, "(lower = fingers must be closer)"))
    parts.append(f'''
<rect x="{sx}" y="{y-12}" width="15" height="15" rx="3" fill="none" stroke="#aaa" stroke-width="1.5"/>
<text {FONT} x="{sx+24}" y="{y}" fill="#eee" font-size="14">Invert direction</text>
<rect x="{sx+170}" y="{y-12}" width="15" height="15" rx="3" fill="#8ab4f8"/>
<path d="M{sx+173} {y-4.5} l3 3 l6 -6" stroke="#111" stroke-width="2" fill="none" stroke-linecap="round"/>
<text {FONT} x="{sx+194}" y="{y}" fill="#eee" font-size="14">Momentum</text>''')
    y += 22
    parts.append(f'<rect x="{sx}" y="{y}" width="{sw}" height="36" rx="8" fill="{GREEN}"/>'
                 f'<text {FONT} x="{sx+sw/2}" y="{y+23}" text-anchor="middle" fill="#012" font-size="14" font-weight="700">Run in background (hide camera)</text>')
    y += 44
    parts.append(f'<rect x="{sx}" y="{y}" width="{sw}" height="36" rx="8" fill="#333"/>'
                 f'<text {FONT} x="{sx+sw/2}" y="{y+23}" text-anchor="middle" fill="#fff" font-size="14" font-weight="700">Pop out (always on top)</text>')
    return parts


def render(name, parts):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">\n' + "\n".join(parts) + "\n</svg>\n"
    svg_path = os.path.join(HERE, f"{name}.svg")
    with open(svg_path, "w") as f:
        f.write(svg)
    subprocess.run(["rsvg-convert", svg_path, "-o", os.path.join(HERE, f"{name}.png")], check=True)
    print(f"{name}.png")


if __name__ == "__main__":
    render("1-gesture", shot_gesture())
    render("2-background", shot_background())
    render("3-settings", shot_settings())
