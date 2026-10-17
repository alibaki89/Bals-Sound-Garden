"""Procedural animal painters, built on the exact same drawing language as the
cat in ``render/cat.py``.

This is the redesigned animal art system.  Every creature is drawn with the same
handful of habits that make the cat charming, so the whole cast reads as the work
of one hand:

* a big round chibi head sitting high and forward over a soft little body
* a 1px warm outline made by drawing each shape one pixel bigger underneath
* one soft highlight ellipse up-and-left (a single shared light source) plus a
  gentle two-tone underside so bodies feel rounded, not flat
* an always-charming face: soft blue-grey dot-eyes with a white catchlight,
  little pink blush, a simple nose / mouth, and the cat's blink / happy / sad /
  angry / sleeping moods
* nested 3-layer ears, stubby legs with a paw dab, fluffy outlined tails
* a soft translucent contact shadow on the ground

Nothing is loaded from an image.  Everything is ellipses, circles, polygons and
lines, exactly like the cat.  ``draw_animal`` at the bottom owns the animation
timing (idle breathing, walk swing + head bob + ear twitch, hop, cozy lying
sleep, play) and hands each painter a small ``a`` dict of pose flags, so the
painters only describe how an animal looks.

  >>> WHERE TO TUNE THE LOOK <<<
  * per-species SIZE / proportions ...... the body_w/body_h/head-radius numbers
                                          inside each ``_draw_*`` painter
  * per-species relative scale beside the cat ...... ``draw_scale`` in
                                          ``entities/animals.py`` (SPECIES table)
  * animation speed / amount ............ ``_WALK_F`` and the pose maths in
                                          ``draw_animal`` below
  * which species exist / how common .... the SPECIES table + spawn weights in
                                          ``entities/animals.py``
"""

import math

import pygame

from ..utils import ri, clamp, lerp, lerp_color


# --- the shared face palette, taken straight from the cat ------------------
EYE = (54, 58, 70)          # soft blue-grey, never pure black
WHITE = (255, 255, 255)
TEAR = (150, 205, 245)
PINK_NOSE = (240, 128, 140)

_WALK_F = 9.0               # ART: walk-cycle frequency (matches the cat)


# ===========================================================================
# tiny shape helpers - all centre-based so the painters read cleanly
# ===========================================================================
def _fell(surf, col, x0, y0, w, h):
    pygame.draw.ellipse(surf, col, (ri(x0), ri(y0), max(1, ri(w)), max(1, ri(h))))


def _oell(surf, fur, out, cx, cy, hw, hh):
    """Outlined ellipse by centre + half-extents (the cat's body trick)."""
    x0, y0 = ri(cx - hw), ri(cy - hh)
    w, h = max(1, ri(hw * 2)), max(1, ri(hh * 2))
    pygame.draw.ellipse(surf, out, (x0 - 1, y0 - 1, w + 2, h + 2))
    pygame.draw.ellipse(surf, fur, (x0, y0, w, h))


def _ocirc(surf, fur, out, cx, cy, r):
    """Outlined circle by centre + radius."""
    rr = max(2, ri(r))
    pygame.draw.circle(surf, out, (ri(cx), ri(cy)), rr + 1)
    pygame.draw.circle(surf, fur, (ri(cx), ri(cy)), rr)


def _ringc(surf, col, cx, cy, r, w):
    pygame.draw.circle(surf, col, (ri(cx), ri(cy)), max(1, ri(r)), max(1, ri(w)))


def _opoly(surf, fur, out, pts):
    p = [(ri(a), ri(b)) for a, b in pts]
    pygame.draw.polygon(surf, out, p)
    cxx = sum(q[0] for q in p) / len(p)
    cyy = sum(q[1] for q in p) / len(p)
    inner = [(ri(lerp(q[0], cxx, 0.16)), ri(lerp(q[1], cyy, 0.16))) for q in p]
    pygame.draw.polygon(surf, fur, inner)


def _hi(surf, fur_l, cx, cy, hw, hh):
    """One soft highlight ellipse, up and to the left like the cat's."""
    _fell(surf, fur_l, cx - hw, cy - hh, hw * 2, hh * 2)


def _under(surf, col, cx, cy, hw, hh):
    """A soft lighter underside ellipse, for a rounded two-tone belly."""
    _fell(surf, col, cx - hw, cy - hh, hw * 2, hh * 2)


def _ear_tri(surf, p1, p2, p3, fur, out, inner=None):
    """A 3-layer nested triangle ear, exactly like the cat's ears."""
    p = [(ri(p1[0]), ri(p1[1])), (ri(p2[0]), ri(p2[1])), (ri(p3[0]), ri(p3[1]))]
    pygame.draw.polygon(surf, out, p)
    cxx = sum(q[0] for q in p) / 3.0
    cyy = sum(q[1] for q in p) / 3.0
    fp = [(ri(lerp(q[0], cxx, 0.30)), ri(lerp(q[1], cyy, 0.30))) for q in p]
    pygame.draw.polygon(surf, fur, fp)
    if inner is not None:
        ip = [(ri(lerp(q[0], cxx, 0.58)), ri(lerp(q[1], cyy, 0.58))) for q in p]
        pygame.draw.polygon(surf, inner, ip)


def _round_ear(surf, cx, cy, r, fur, out, inner=None):
    _ocirc(surf, fur, out, cx, cy, r)
    if inner is not None:
        pygame.draw.circle(surf, inner, (ri(cx), ri(cy)), max(1, ri(r * 0.5)))


def _drop_ear(surf, cx, cy, hw, hh, fur, out, inner=None):
    """A soft hanging (floppy) ear as an outlined ellipse."""
    _oell(surf, fur, out, cx, cy, hw, hh)
    if inner is not None:
        _oell(surf, inner, out, cx, cy + hh * 0.18, hw * 0.55, hh * 0.6)


def _tail(surf, pts, rads, s, fur, fur_l, out):
    """Fluffy outlined tail: outline every blob first, then fill, then a tip
    highlight, so the whole tail shares one clean silhouette (cat method)."""
    dense = []
    for i in range(len(pts) - 1):
        for f in (0.0, 0.5):
            dense.append((lerp(pts[i][0], pts[i + 1][0], f),
                          lerp(pts[i][1], pts[i + 1][1], f),
                          lerp(rads[i], rads[i + 1], f)))
    dense.append((pts[-1][0], pts[-1][1], rads[-1]))
    for px, py, r in dense:
        pygame.draw.circle(surf, out, (ri(px), ri(py)), max(1, ri(r * s) + 1))
    for px, py, r in dense:
        pygame.draw.circle(surf, fur, (ri(px), ri(py)), max(1, ri(r * s)))
    pygame.draw.circle(surf, fur_l, (ri(pts[-1][0]), ri(pts[-1][1])), max(1, ri(rads[-1] * 0.55 * s)))


# ===========================================================================
# the face - the heart of the cat's cuteness, reused for every animal
# ===========================================================================
def _dot_eye(surf, c, s, col=EYE, dy=0.0):
    es = max(2, ri(3.0 * s))
    rx, ry = ri(c[0] - es / 2), ri(c[1] - es / 2 + dy)
    pygame.draw.rect(surf, col, (rx, ry, es, es))
    surf.set_at((clamp(rx, 0, surf.get_width() - 1),
                 clamp(ry, 0, surf.get_height() - 1)), WHITE)   # catchlight pixel


def _closed_eye(surf, c, s, col=EYE):
    """A soft happy-closed arc (gentler than a flat line)."""
    pts = [(ri(c[0] - 3 * s), ri(c[1] - 0.5 * s)),
           (ri(c[0]), ri(c[1] + 0.6 * s)),
           (ri(c[0] + 3 * s), ri(c[1] - 0.5 * s))]
    pygame.draw.lines(surf, col, False, pts, max(1, ri(1.4 * s)))


def _happy_eye(surf, c, s, col=EYE):
    a = (ri(c[0] - 3 * s), ri(c[1] + 1 * s))
    b = (ri(c[0]), ri(c[1] - 2 * s))
    d = (ri(c[0] + 3 * s), ri(c[1] + 1 * s))
    pygame.draw.lines(surf, col, False, [a, b, d], max(1, ri(1.5 * s)))


def _big_eye(surf, c, s, out, dy=0.0):
    """A round shiny eye for frogs, owls, birds, ducks."""
    r = max(2, ri(3.6 * s))
    cx, cy = ri(c[0]), ri(c[1] + dy)
    pygame.draw.circle(surf, out, (cx, cy), r + 1)
    pygame.draw.circle(surf, WHITE, (cx, cy), r)
    pr = max(1, ri(2.2 * s))
    pygame.draw.circle(surf, EYE, (cx + max(1, ri(0.4 * s)), cy + max(0, ri(0.4 * s))), pr)
    surf.set_at((clamp(cx - max(1, ri(0.7 * s)), 0, surf.get_width() - 1),
                 clamp(cy - max(1, ri(0.7 * s)), 0, surf.get_height() - 1)), WHITE)


def _blush(surf, cx, cy, s, col):
    pygame.draw.rect(surf, col, (ri(cx - 2 * s), ri(cy), max(2, ri(4 * s)), max(1, ri(2 * s))))


def _brows(surf, el, er, s, out, kind):
    if kind == "angry":
        pygame.draw.line(surf, out, (ri(el[0] - 3 * s), ri(el[1] - 6 * s)),
                         (ri(el[0] + 3 * s), ri(el[1] - 3 * s)), max(1, ri(1.4 * s)))
        pygame.draw.line(surf, out, (ri(er[0] + 3 * s), ri(er[1] - 6 * s)),
                         (ri(er[0] - 3 * s), ri(er[1] - 3 * s)), max(1, ri(1.4 * s)))
    elif kind == "sad":
        pygame.draw.line(surf, out, (ri(el[0] - 3 * s), ri(el[1] - 5 * s)),
                         (ri(el[0] + 2 * s), ri(el[1] - 6 * s)), max(1, ri(1 * s)))
        pygame.draw.line(surf, out, (ri(er[0] - 2 * s), ri(er[1] - 6 * s)),
                         (ri(er[0] + 3 * s), ri(er[1] - 5 * s)), max(1, ri(1 * s)))


def face(surf, hx, hy, hr, s, a, *, eye_dx=6.0, eye_dy=-0.5, nose=True,
         nose_c=PINK_NOSE, nose_dy=5.0, mouth="y", mouth_w=4.0, blush=True,
         blush_c=None, big_eyes=False, eye_out=None, eye_col=EYE):
    """Paint a cat-style face centred on a head at (hx, hy) of radius hr.

    ``mouth`` is one of ``y`` / ``smile`` / ``none``.  ``big_eyes`` swaps the
    tiny dot-eyes for round shiny eyes (frog, owl, bird, duck).
    """
    mood = a["mood"]
    blink = a["blink"]
    sleeping = a["sleeping"]
    ex = eye_dx * s
    ey = hy + eye_dy * s
    el = (hx - ex, ey)
    er = (hx + ex, ey)
    if blush_c is None:
        blush_c = (255, 174, 184)

    if sleeping or blink:
        _closed_eye(surf, el, s)
        _closed_eye(surf, er, s)
    elif mood == "happy":
        _happy_eye(surf, el, s)
        _happy_eye(surf, er, s)
    elif big_eyes:
        eo = eye_out if eye_out is not None else (96, 110, 120)
        _big_eye(surf, el, s, eo)
        _big_eye(surf, er, s, eo)
    else:
        _dot_eye(surf, el, s, eye_col, dy=(1.2 * s if mood == "sad" else 0.0))
        _dot_eye(surf, er, s, eye_col, dy=(1.2 * s if mood == "sad" else 0.0))
        if mood in ("angry", "sad"):
            _brows(surf, el, er, s, EYE, mood)

    if nose:
        pygame.draw.circle(surf, nose_c, (ri(hx), ri(hy + nose_dy * s)), max(1, ri(1.7 * s)))

    ny = hy + (nose_dy + 0.5) * s
    if mouth == "smile" or mood == "happy":
        pygame.draw.arc(surf, EYE, (ri(hx - mouth_w * s), ri(ny - 1 * s),
                                    ri(mouth_w * 2 * s), ri((mouth_w + 3) * s)),
                        1.15 * math.pi, 1.85 * math.pi, max(1, ri(1.4 * s)))
    elif mouth == "y":
        pygame.draw.line(surf, EYE, (ri(hx), ri(ny - 1 * s)), (ri(hx), ri(ny + 1.5 * s)), max(1, ri(1 * s)))
        pygame.draw.line(surf, EYE, (ri(hx), ri(ny + 1.5 * s)), (ri(hx - 2.5 * s), ri(ny + 3 * s)), max(1, ri(1 * s)))
        pygame.draw.line(surf, EYE, (ri(hx), ri(ny + 1.5 * s)), (ri(hx + 2.5 * s), ri(ny + 3 * s)), max(1, ri(1 * s)))

    if blush and mood != "angry":
        _blush(surf, hx - hr * 0.66, hy + 2.5 * s, s, blush_c)
        _blush(surf, hx + hr * 0.66 - 4 * s, hy + 2.5 * s, s, blush_c)


def _zzz(surf, x, y, s, t):
    for i in range(2):
        zz = (t * 1.4 + i * 0.5) % 2.0
        zx = ri(x + i * 4 * s + zz * 2 * s)
        zy = ri(y - zz * 5 * s)
        zs = max(2, ri(3 * s))
        pygame.draw.line(surf, WHITE, (zx, zy), (zx + zs, zy), max(1, ri(1 * s)))
        pygame.draw.line(surf, WHITE, (zx + zs, zy), (zx, zy + zs), max(1, ri(1 * s)))
        pygame.draw.line(surf, WHITE, (zx, zy + zs), (zx + zs, zy + zs), max(1, ri(1 * s)))


def _sparkle(surf, x, y, s):
    c = (255, 246, 210)
    r = max(2, ri(2.4 * s))
    pygame.draw.line(surf, c, (ri(x - r), ri(y)), (ri(x + r), ri(y)), max(1, ri(1 * s)))
    pygame.draw.line(surf, c, (ri(x), ri(y - r)), (ri(x), ri(y + r)), max(1, ri(1 * s)))


def _fshade(surf, col, cx, cy, hw, hh):
    """A soft form-shadow / rim ellipse, for rounded volume and back light."""
    _fell(surf, col, cx - hw, cy - hh, hw * 2, hh * 2)


def _pg(surf, col, pts):
    """Filled polygon from float points (rounds each to a pixel)."""
    pygame.draw.polygon(surf, col, [(ri(x), ri(y)) for x, y in pts])


def _legA(surf, hipx, hipy, fx, fy, w, col, sock, hoof, out, bend=0.0, hoofed=False):
    """A jointed leg: thigh (body tone) -> cannon (darker sock) -> hoof / paw.

    The knee/hock gives legs anatomy so they read as limbs, not sticks."""
    kx = lerp(hipx, fx, 0.5) + bend
    ky = lerp(hipy, fy, 0.54)
    pygame.draw.line(surf, col, (ri(hipx), ri(hipy)), (ri(kx), ri(ky)), max(2, ri(w)))
    pygame.draw.line(surf, sock, (ri(kx), ri(ky)), (ri(fx), ri(fy)), max(2, ri(w - 1.5)))
    if hoofed:
        _oell(surf, hoof, out, fx, fy - 0.4, w * 0.5, w * 0.34)
    else:
        _oell(surf, sock, out, fx, fy, w * 0.5, w * 0.32)


def _ungulate(surf, cx, gy, s, fur, fur_d, fur_l, out, a, *, body_w, body_h,
              body_lift, leg_w, sock=None, hoof=(70, 60, 58), belly=None,
              stride=3.0, lift=3.0, hoofed=True):
    """A shaped hoofed body: chest + barrel + rump under one silhouette, a back
    rim-light and a belly form-shadow, and four jointed legs on a believable
    diagonal gait.  Returns anchors for the neck / head / tail."""
    rest = a["rest"]
    lean = a["lean"] * s
    air = a["airborne"]
    step = a["step"]
    lift_eff = body_lift * 0.42 if rest else body_lift
    bob = a["bob"]
    bcx = cx + lean * 0.5
    bcy = gy - lift_eff * s + bob
    bw, bh = body_w * s, body_h * s
    if rest:
        bw *= 1.12
        bh *= 0.80
    ground = gy - 1.0 * s
    body_bottom = bcy + bh * 0.5
    if sock is None:
        sock = fur_d
    lw = max(2, leg_w * s)
    stride_s = stride * s
    lift_s = lift * s
    hipy = bcy + bh * 0.30
    fnx, ffx = bcx + bw * 0.30, bcx + bw * 0.20
    hnx, hfx = bcx - bw * 0.26, bcx - bw * 0.16
    chx, rmx = bcx + bw * 0.30, bcx - bw * 0.32

    def foot(fx, phase):
        if air:
            return (fx, body_bottom + 5.0 * s)
        if rest:
            return (fx, body_bottom + 2.0 * s)
        return (fx + phase * stride_s, ground - max(0.0, phase) * lift_s)

    def body_outline(grow):
        _fell(surf, out, bcx - bw * 0.5 - grow, bcy - bh * 0.5 - grow, bw + grow * 2, bh + grow * 2)
        _fell(surf, out, chx - bh * 0.5 - grow, bcy - bh * 0.46 - grow, bh + grow * 2, bh * 0.92 + grow * 2)
        _fell(surf, out, rmx - bh * 0.55 - grow, bcy - bh * 0.5 - grow, bh * 1.1 + grow * 2, bh + grow * 2)

    if rest:
        _legA(surf, bcx - bw * 0.22, body_bottom, bcx - bw * 0.30, body_bottom + 2 * s, lw, fur_d, sock, hoof, out, 0, hoofed)
        _legA(surf, bcx + bw * 0.22, body_bottom, bcx + bw * 0.30, body_bottom + 2 * s, lw, fur_d, sock, hoof, out, 0, hoofed)
    else:
        fh = foot(hfx, step); fft = foot(ffx, -step)
        _legA(surf, hfx, hipy, fh[0], fh[1], lw - 1, fur_d, fur_d, hoof, out, -2 * s, hoofed)
        _legA(surf, ffx, hipy, fft[0], fft[1], lw - 1, fur_d, fur_d, hoof, out, 1.5 * s, hoofed)

    body_outline(1)
    _fell(surf, fur, bcx - bw * 0.5, bcy - bh * 0.5, bw, bh)
    _fell(surf, fur, chx - bh * 0.5, bcy - bh * 0.46, bh, bh * 0.92)
    _fell(surf, fur, rmx - bh * 0.55, bcy - bh * 0.5, bh * 1.1, bh)
    if belly is not None:
        _fshade(surf, belly, bcx + bw * 0.02, bcy + bh * 0.22, bw * 0.40, bh * 0.30)
    _fshade(surf, fur_d, rmx, bcy + bh * 0.18, bh * 0.5, bh * 0.34)
    _fshade(surf, fur_l, bcx - bw * 0.04, bcy - bh * 0.34, bw * 0.46, bh * 0.20)
    _hi(surf, fur_l, bcx - bw * 0.20, bcy - bh * 0.22, bw * 0.20, bh * 0.18)
    if not rest:
        fhn = foot(hnx, -step); ffn = foot(fnx, step)
        _legA(surf, hnx, hipy, fhn[0], fhn[1], lw, fur, sock, hoof, out, -2.5 * s, hoofed)
        _legA(surf, fnx, hipy, ffn[0], ffn[1], lw, fur, sock, hoof, out, 1.5 * s, hoofed)

    return dict(bcx=bcx, bcy=bcy, bw=bw, bh=bh, body_bottom=body_bottom, rest=rest, lean=lean,
                withers=(bcx + bw * 0.18, bcy - bh * 0.46), croup=(bcx - bw * 0.34, bcy - bh * 0.36),
                chest=(bcx + bw * 0.46, bcy - bh * 0.06), rump=(bcx - bw * 0.48, bcy - bh * 0.04))


# ===========================================================================
# a shared quadruped base: soft body + four stubby swinging legs, a forward
# lean while walking and a cozy folded "rest" pose for sleeping.
# ===========================================================================
def _quad(surf, cx, gy, s, fur, fur_d, fur_l, out, a, *, body_w, body_h,
          body_lift, leg_w, belly=None, stride=4.0, lift=3.2):
    rest = a["rest"]
    lean = a["lean"] * s
    lift_eff = body_lift * 0.42 if rest else body_lift
    bob = a["bob"]
    bcx = cx + lean * 0.5
    bcy = gy - lift_eff * s + bob
    bw, bh = body_w * s, body_h * s
    if rest:
        bw *= 1.10
        bh *= 0.86
    body_bottom = bcy + bh * 0.45
    ground = gy - 1.0 * s
    stride_s = stride * s
    lift_s = lift * s
    step = a["step"]
    airborne = a["airborne"]

    def foot(fx, sign):
        if airborne:
            return (fx, body_bottom + 3.0 * s)
        if rest:
            return (fx, body_bottom + 1.5 * s)
        sg = step * sign
        return (fx + sg * stride_s, ground - max(0.0, sg) * lift_s)

    nb_x = bcx - bw * 0.30
    nf_x = bcx + bw * 0.27
    fb_x = bcx - bw * 0.20
    ff_x = bcx + bw * 0.17
    nb, nf = foot(nb_x, -1.0), foot(nf_x, +1.0)
    fb, ff = foot(fb_x, +1.0), foot(ff_x, -1.0)
    hipy = body_bottom - 1.0 * s

    def leg(hipx, ft, far):
        up = fur_d if far else fur
        lo = fur_d
        w = max(2, ri((leg_w - 1 if far else leg_w) * s))
        if rest:
            pw = max(2, ri((leg_w + 2) * s))
            _fell(surf, lo, ft[0] - pw * 0.5, ft[1] - 1.4 * s, pw, max(1, ri(2.6 * s)))
            return
        kx, ky = lerp(hipx, ft[0], 0.5), lerp(hipy, ft[1], 0.5)
        pygame.draw.line(surf, up, (ri(hipx), ri(hipy)), (ri(kx), ri(ky)), w)
        pygame.draw.line(surf, lo, (ri(kx), ri(ky)), (ri(ft[0]), ri(ft[1])), max(2, w - 1))
        pw = max(2, ri((leg_w + 1.5) * s))
        _fell(surf, lo, ft[0] - pw * 0.4, ft[1] - 1.1 * s, pw, max(1, ri(2.4 * s)))

    if not rest:
        leg(fb_x, fb, True)
        leg(ff_x, ff, True)

    _oell(surf, fur, out, bcx, bcy, bw * 0.5, bh * 0.5)
    if belly is not None:
        _under(surf, belly, bcx + bw * 0.04, bcy + bh * 0.20, bw * 0.36, bh * 0.34)
    _fshade(surf, fur_d, bcx - bw * 0.32, bcy + bh * 0.14, bw * 0.24, bh * 0.24)
    _fshade(surf, fur_l, bcx - bw * 0.02, bcy - bh * 0.34, bw * 0.40, bh * 0.16)
    _hi(surf, fur_l, bcx - bw * 0.22, bcy - bh * 0.18, bw * 0.24, bh * 0.22)

    if rest:
        leg(fb_x + bw * 0.1, (bcx - bw * 0.24, body_bottom), False)
        leg(nf_x, (bcx + bw * 0.30, body_bottom), False)
    else:
        leg(nb_x, nb, False)
        leg(nf_x, nf, False)

    return dict(bcx=bcx, bcy=bcy, bw=bw, bh=bh, body_bottom=body_bottom,
                rest=rest, lean=lean,
                rear=(bcx - bw * 0.46, bcy - bh * 0.04),
                front=(bcx + bw * 0.42, bcy - bh * 0.08))


# ===========================================================================
# PRIORITY SPECIES - drawn with the most care, matched to the cat
# ===========================================================================
def _draw_dog(surf, cx, gy, s, a):
    fur = (222, 170, 112); fur_d = (190, 140, 86); fur_l = (244, 210, 158); out = (136, 94, 56)
    muzzle = (248, 228, 196); ear_in = (224, 168, 150); nose_c = (54, 42, 42); tongue = (238, 138, 140)
    k = _quad(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
              body_w=46, body_h=26, body_lift=16, leg_w=5.5, belly=fur_l)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    sway = math.sin(a["t"] * 5.0) * 3.0 * s
    _tail(surf, [k["rear"], (k["rear"][0] - 6 * s, k["rear"][1] - 6 * s),
                 (k["rear"][0] - 9 * s, k["rear"][1] - 15 * s + sway), (k["rear"][0] - 4 * s, k["rear"][1] - 21 * s + sway)],
          [3.8, 3.6, 3.2, 2.4], s, fur, fur_l, out)
    hh = a["headbob"]; et = a["ear"]
    hx, hy, hr = bcx + bw * 0.5, bcy - bh * (0.42 if k["rest"] else 0.78) + hh, 14.5 * s
    # erect triangular ears with soft folded tips (reads clearly "dog")
    _ear_tri(surf, (hx - hr * 0.66, hy - hr * 0.4 + et), (hx - hr * 0.14, hy - hr * 0.5),
             (hx - hr * 0.66, hy - hr * 1.4), fur, out, ear_in)
    _ear_tri(surf, (hx + hr * 0.14, hy - hr * 0.5), (hx + hr * 0.66, hy - hr * 0.4 - et),
             (hx + hr * 0.66, hy - hr * 1.4), fur, out, ear_in)
    _pg(surf, fur_d, [(hx - hr * 0.66, hy - hr * 1.4), (hx - hr * 0.8, hy - hr * 1.0), (hx - hr * 0.42, hy - hr * 1.04)])
    _pg(surf, fur_d, [(hx + hr * 0.66, hy - hr * 1.4), (hx + hr * 0.8, hy - hr * 1.0), (hx + hr * 0.42, hy - hr * 1.04)])
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.3, hy - hr * 0.36, hr * 0.34, hr * 0.3)
    # blunt forward muzzle + open happy smile, tongue, black nose, philtrum
    _oell(surf, muzzle, out, hx + hr * 0.28, hy + hr * 0.52, hr * 0.64, hr * 0.52)
    pygame.draw.arc(surf, out, (ri(hx - hr * 0.06), ri(hy + hr * 0.5), ri(hr * 0.98), ri(hr * 0.66)),
                    1.1 * math.pi, 1.9 * math.pi, max(1, ri(1.3 * s)))
    if not a["sleeping"]:
        pygame.draw.circle(surf, tongue, (ri(hx + hr * 0.42), ri(hy + hr * 0.96)), max(1, ri(1.8 * s)))
    pygame.draw.circle(surf, nose_c, (ri(hx + hr * 0.44), ri(hy + hr * 0.34)), max(1, ri(2.4 * s)))
    pygame.draw.line(surf, out, (ri(hx + hr * 0.44), ri(hy + hr * 0.5)), (ri(hx + hr * 0.44), ri(hy + hr * 0.66)), max(1, ri(1 * s)))
    face(surf, hx, hy - hr * 0.05, hr, s, a, eye_dx=4.8, eye_dy=-1.0, nose=False, mouth="none", blush=True, blush_c=(244, 176, 150))


def _draw_rabbit(surf, cx, gy, s, a):
    fur = (248, 242, 236); fur_d = (218, 210, 202); fur_l = (255, 255, 253)
    out = (176, 154, 142); ear_in = (250, 196, 206)
    bob = a["bob"]; air = a["airborne"]; rest = a["rest"]
    bcx = cx
    bcy = gy - (20 if air else (9 if rest else 16)) * s + bob
    bw, bh = 24.0 * s, 26.0 * s
    if rest:
        bw *= 1.18; bh *= 0.82
    body_bottom = bcy + bh * 0.7
    if air:
        pygame.draw.line(surf, fur_d, (ri(bcx - 5 * s), ri(body_bottom - 2 * s)),
                         (ri(bcx - 8 * s), ri(body_bottom + 3 * s)), max(2, ri(4.5 * s)))
        pygame.draw.line(surf, fur_d, (ri(bcx + 5 * s), ri(body_bottom - 2 * s)),
                         (ri(bcx + 8 * s), ri(body_bottom + 3 * s)), max(2, ri(4.5 * s)))
    elif not rest:
        _oell(surf, fur, out, bcx - bw * 0.46, body_bottom - 1 * s, 5.5 * s, 2.8 * s)
        _oell(surf, fur, out, bcx + bw * 0.46, body_bottom - 1 * s, 5.5 * s, 2.8 * s)
    pygame.draw.circle(surf, out, (ri(bcx - bw * 0.72), ri(bcy + bh * 0.22)), max(2, ri(3.6 * s)) + 1)
    pygame.draw.circle(surf, fur_l, (ri(bcx - bw * 0.72), ri(bcy + bh * 0.22)), max(2, ri(3.6 * s)))
    _oell(surf, fur, out, bcx, bcy, bw * 0.5, bh * 0.5)
    _under(surf, fur_l, bcx, bcy + bh * 0.22, bw * 0.34, bh * 0.30)
    _hi(surf, fur_l, bcx - bw * 0.2, bcy - bh * 0.18, bw * 0.26, bh * 0.26)
    hh = a["headbob"]
    hx, hy, hr = bcx + bw * 0.06, bcy - bh * (0.30 if rest else 0.46) + hh, 13.0 * s
    ew = a["ear"] * 0.6
    if rest:
        for sgn in (-1, 1):
            _oell(surf, fur, out, hx - hr * 1.4, hy - hr * 0.1 + sgn * hr * 0.3, hr * 0.9, hr * 0.28)
            _oell(surf, ear_in, out, hx - hr * 1.3, hy - hr * 0.1 + sgn * hr * 0.3, hr * 0.5, hr * 0.14)
    else:
        for sgn in (-1, 1):
            ex = hx + sgn * hr * 0.42
            _oell(surf, fur, out, ex + sgn * ew, hy - hr * 1.48, hr * 0.34, hr * 1.05)
            _oell(surf, ear_in, out, ex + sgn * ew, hy - hr * 1.42, hr * 0.16, hr * 0.74)
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.32, hy - hr * 0.3, hr * 0.32, hr * 0.3)
    face(surf, hx, hy, hr, s, a, eye_dx=4.8, nose_c=(236, 150, 168), nose_dy=4.2, mouth="y")


def _draw_deer(surf, cx, gy, s, a):
    fur = (214, 158, 102); fur_d = (184, 128, 78); fur_l = (240, 198, 150); out = (136, 92, 54)
    belly = (248, 232, 210); white = (250, 246, 238); spot = (252, 242, 218)
    antler = (178, 138, 94); antler_d = (148, 108, 70); antler_l = (206, 172, 128); hoof = (64, 52, 48)
    nose_c = (56, 44, 44); ear_in = (244, 202, 202)
    hh = a["headbob"]; rest = a["rest"]; lean = a["lean"] * s
    k = _ungulate(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
                  body_w=42, body_h=19, body_lift=26, leg_w=3.4, stride=3.2, lift=3.4,
                  sock=fur_d, hoof=hoof, belly=belly, hoofed=True)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    # tidy white spots in a clean arc along the topline / upper flank
    for dx, dy, r in ((-0.30, -0.32, 1.3), (-0.13, -0.36, 1.3), (0.05, -0.33, 1.2),
                      (0.20, -0.25, 1.1), (-0.22, -0.18, 1.1), (-0.03, -0.20, 1.1)):
        pygame.draw.circle(surf, spot, (ri(bcx + bw * dx), ri(bcy + bh * dy)), max(1, ri(r * s)))
    # a clear fluffy tail sweeping up-and-back off the rump, with a white underside
    _tail(surf, [(bcx - bw * 0.50, bcy - bh * 0.02), (bcx - bw * 0.66, bcy - bh * 0.16),
                 (bcx - bw * 0.73, bcy - bh * 0.40)], [3.2, 2.8, 1.9], s, fur, fur_l, out)
    _oell(surf, white, out, bcx - bw * 0.64, bcy - bh * 0.20, 1.3 * s, 2.4 * s)

    u = 7.2 * s
    hx = bcx + bw * (0.56 if rest else 0.74) + lean * 0.4
    hy = bcy - bh * (0.4 if rest else 1.18) + hh
    C = (hx, hy); M = (hx + u * 0.92, hy + u * 0.82)
    # slender neck (outline-first, then fill) with a cream throat
    Hbt = (hx - u * 0.64, hy - u * 0.12); Hbb = (hx - u * 0.30, hy + u * 0.96)
    W = (bcx + bw * 0.16, bcy - bh * 0.5); Cf = (bcx + bw * 0.5, bcy - bh * 0.04)
    _pg(surf, out, [Hbt, W, Cf, Hbb])
    _pg(surf, fur, [(Hbt[0] + 0.8 * s, Hbt[1] + 0.8 * s), (W[0] + 1.4 * s, W[1] + 1 * s),
                    (Cf[0] - 0.8 * s, Cf[1] - 0.8 * s), (Hbb[0] + 0.6 * s, Hbb[1] - 0.4 * s)])
    pygame.draw.line(surf, white, (ri(lerp(Cf[0], Hbb[0], 0.25)), ri(lerp(Cf[1], Hbb[1], 0.25))),
                     (ri(Hbb[0] + 1 * s), ri(Hbb[1] - 1 * s)), max(2, ri(2.4 * s)))

    # big soft ears (the hero), drawn behind the head
    et = a["ear"]

    def ear(exx, eyy, inx):
        _oell(surf, fur, out, exx, eyy, u * 0.4, u * 0.9)
        _oell(surf, ear_in, out, exx + inx, eyy + u * 0.08, u * 0.2, u * 0.6)

    ear(hx - u * 0.66, hy - u * 0.66 + et, u * 0.05)
    ear(hx + u * 0.52, hy - u * 0.78 - et, -u * 0.05)
    # tiny velvet antler buds (soft + cute, not scary)
    for sgn in (-1, 1):
        bx, by = hx + sgn * u * 0.18, hy - u * 0.84
        pygame.draw.line(surf, antler, (ri(bx), ri(by)), (ri(bx + sgn * u * 0.12), ri(by - u * 0.48)), max(2, ri(2.8 * s)))
        _ocirc(surf, antler_l, antler_d, bx + sgn * u * 0.14, by - u * 0.54, 2.0 * s)
    # head: rounded cranium + tapered muzzle under one smooth outline
    def head_parts(col, g):
        _fell(surf, col, C[0] - u * 1.0 - g, C[1] - u * 1.04 - g, u * 2.0 + g * 2, u * 2.08 + g * 2)
        _fell(surf, col, M[0] - u * 0.6 - g, M[1] - u * 0.5 - g, u * 1.2 + g * 2, u * 1.0 + g * 2)

    head_parts(out, 1)
    head_parts(fur, 0)
    _oell(surf, white, out, M[0] + u * 0.12, M[1] + u * 0.04, u * 0.44, u * 0.38)
    pygame.draw.circle(surf, nose_c, (ri(M[0] + u * 0.34), ri(M[1] - u * 0.04)), max(1, ri(1.9 * s)))
    pygame.draw.line(surf, out, (ri(M[0] + u * 0.04), ri(M[1] + u * 0.3)), (ri(M[0] + u * 0.34), ri(M[1] + u * 0.26)), max(1, ri(1 * s)))
    _hi(surf, fur_l, hx - u * 0.32, hy - u * 0.4, u * 0.34, u * 0.36)
    # single soft eye with a big catchlight (gentle, not a hard stare)
    ex, ey = hx + u * 0.18, hy - u * 0.02
    if a["sleeping"] or a["blink"]:
        _closed_eye(surf, (ex, ey), s)
    else:
        er = max(2, ri(2.5 * s))
        pygame.draw.circle(surf, out, (ri(ex), ri(ey)), er + 1)
        pygame.draw.circle(surf, (62, 50, 52), (ri(ex), ri(ey)), er)
        pygame.draw.circle(surf, WHITE, (ri(ex - 0.7 * s), ri(ey - 0.8 * s)), max(1, ri(1.0 * s)))
    if a["mood"] != "angry":
        _blush(surf, hx - u * 0.18, hy + u * 0.30, s, (246, 180, 158))


def _draw_sheep(surf, cx, gy, s, a):
    wool = (248, 246, 240); wool_l = (255, 255, 253); out = (178, 168, 158)
    face_c = (170, 152, 144); face_d = (136, 120, 114); leg_c = (120, 108, 108); leg_d = (94, 84, 84)
    bob = a["bob"]; rest = a["rest"]
    bcx = cx
    bcy = gy - (11 if rest else 18) * s + bob
    bw, bh = 42.0 * s, 30.0 * s
    if rest:
        bw *= 1.08; bh *= 0.9
    body_bottom = bcy + bh * 0.42
    ground = gy - 1.0 * s
    step = a["step"]; air = a["airborne"]
    hipy = body_bottom - 1.0 * s
    if not rest:
        for lx, sign in ((bcx - bw * 0.26, -1), (bcx + bw * 0.24, 1),
                         (bcx - bw * 0.16, 1), (bcx + bw * 0.12, -1)):
            sg = 0.0 if air else step * sign
            fy = ground - max(0.0, sg) * 2.0 * s
            fx = lx + sg * 2.5 * s
            kx, ky = lerp(lx, fx, 0.5), lerp(hipy, fy, 0.52)
            pygame.draw.line(surf, leg_c, (ri(lx), ri(hipy)), (ri(kx), ri(ky)), max(2, ri(3.4 * s)))
            pygame.draw.line(surf, leg_d, (ri(kx), ri(ky)), (ri(fx), ri(fy)), max(2, ri(2.6 * s)))
            _oell(surf, (58, 50, 52), out, fx, fy - 0.4, 2.0 * s, 1.3 * s)
    bumps = []
    n = 10
    for i in range(n):
        ang = math.pi * (0.04 + 0.92 * i / (n - 1))
        bumps.append((bcx - math.cos(ang) * bw * 0.5, bcy - math.sin(ang) * bh * 0.5, 6.6))
    bumps.append((bcx - bw * 0.2, bcy + bh * 0.22, 7.5))
    bumps.append((bcx + bw * 0.2, bcy + bh * 0.22, 7.5))
    for bx, by, r in bumps:
        pygame.draw.circle(surf, out, (ri(bx), ri(by)), max(2, ri(r * s) + 1))
    pygame.draw.ellipse(surf, out, (ri(bcx - bw * 0.5) - 1, ri(bcy - bh * 0.32) - 1, ri(bw) + 2, ri(bh * 0.72) + 2))
    pygame.draw.ellipse(surf, wool, (ri(bcx - bw * 0.5), ri(bcy - bh * 0.32), ri(bw), ri(bh * 0.72)))
    for bx, by, r in bumps:
        pygame.draw.circle(surf, wool, (ri(bx), ri(by)), max(2, ri(r * s)))
    for bx, by, r in bumps[:5]:
        pygame.draw.circle(surf, wool_l, (ri(bx - r * 0.3 * s), ri(by - r * 0.3 * s)), max(1, ri(r * 0.4 * s)))
    _fshade(surf, (218, 214, 204), bcx + bw * 0.04, bcy + bh * 0.26, bw * 0.4, bh * 0.18)
    hh = a["headbob"]
    hx, hy, hr = bcx + bw * 0.50, bcy - bh * 0.08 + hh, 11.0 * s
    et = a["ear"]
    _drop_ear(surf, hx - hr * 0.92, hy - hr * 0.06 + et, hr * 0.46, hr * 0.34, face_d, out)
    _drop_ear(surf, hx + hr * 0.96, hy - hr * 0.06 - et, hr * 0.46, hr * 0.34, face_d, out)
    _oell(surf, face_c, out, hx, hy, hr * 0.82, hr * 0.96)
    pygame.draw.circle(surf, wool, (ri(hx - hr * 0.32), ri(hy - hr * 0.78)), max(1, ri(2.6 * s)))
    pygame.draw.circle(surf, wool, (ri(hx + hr * 0.04), ri(hy - hr * 0.92)), max(1, ri(2.8 * s)))
    pygame.draw.circle(surf, wool, (ri(hx + hr * 0.4), ri(hy - hr * 0.74)), max(1, ri(2.4 * s)))
    face(surf, hx, hy + hr * 0.08, hr, s, a, eye_dx=3.8, nose_c=(148, 122, 118),
         nose_dy=4.0, mouth="none", blush=True, blush_c=(232, 176, 180))


def _draw_cow(surf, cx, gy, s, a):
    base = (250, 247, 242); base_d = (224, 218, 210); base_l = (255, 255, 254)
    out = (160, 146, 138); patch = (92, 80, 76); muzzle = (244, 186, 192)
    horn = (238, 222, 192); hoof = (70, 62, 62)
    hh = a["headbob"]; rest = a["rest"]; lean = a["lean"] * s
    k = _ungulate(surf, cx, gy, s, base, base_d, base_l, out, a,
                  body_w=50, body_h=27, body_lift=18, leg_w=6, stride=2.6, lift=2.6,
                  sock=base_d, hoof=hoof, hoofed=True)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    pygame.draw.ellipse(surf, patch, (ri(bcx - bw * 0.34), ri(bcy - bh * 0.30), ri(bw * 0.34), ri(bh * 0.5)))
    pygame.draw.ellipse(surf, patch, (ri(bcx + bw * 0.10), ri(bcy - bh * 0.02), ri(bw * 0.3), ri(bh * 0.42)))
    pygame.draw.line(surf, out, (ri(k["rump"][0]), ri(k["rump"][1])),
                     (ri(k["rump"][0] - 3 * s), ri(k["rump"][1] + 15 * s)), max(1, ri(1.5 * s)))
    pygame.draw.circle(surf, patch, (ri(k["rump"][0] - 3 * s), ri(k["rump"][1] + 16 * s)), max(1, ri(2.2 * s)))
    hx = bcx + bw * 0.62 + lean * 0.5
    hy = bcy - bh * (0.3 if rest else 0.62) + hh
    hr = 14.5 * s
    _pg(surf, out, [(bcx + bw * 0.32, bcy - bh * 0.42), (hx - hr * 0.4, hy - hr * 0.2),
                    (hx, hy + hr * 0.72), (bcx + bw * 0.46, bcy + bh * 0.06)])
    _pg(surf, base, [(bcx + bw * 0.35, bcy - bh * 0.38), (hx - hr * 0.32, hy - hr * 0.14),
                     (hx - hr * 0.02, hy + hr * 0.62), (bcx + bw * 0.43, bcy + bh * 0.02)])
    et = a["ear"]
    _drop_ear(surf, hx - hr * 1.0, hy + et, hr * 0.5, hr * 0.34, base_d, out)
    _drop_ear(surf, hx + hr * 1.0, hy - et, hr * 0.5, hr * 0.34, base_d, out)
    for sgn in (-1, 1):
        pygame.draw.line(surf, horn, (ri(hx + sgn * hr * 0.45), ri(hy - hr * 0.74)),
                         (ri(hx + sgn * hr * 0.7), ri(hy - hr * 1.05)), max(2, ri(2.4 * s)))
    _ocirc(surf, base, out, hx, hy, hr)
    pygame.draw.circle(surf, patch, (ri(hx - hr * 0.48), ri(hy - hr * 0.24)), max(1, ri(hr * 0.42)))
    _hi(surf, base_l, hx - hr * 0.26, hy - hr * 0.36, hr * 0.3, hr * 0.28)
    _oell(surf, muzzle, out, hx + hr * 0.06, hy + hr * 0.5, hr * 0.66, hr * 0.5)
    pygame.draw.circle(surf, (198, 132, 142), (ri(hx - hr * 0.18), ri(hy + hr * 0.5)), max(1, ri(1.5 * s)))
    pygame.draw.circle(surf, (198, 132, 142), (ri(hx + hr * 0.3), ri(hy + hr * 0.5)), max(1, ri(1.5 * s)))
    face(surf, hx, hy, hr, s, a, eye_dx=5.2, nose=False, mouth="none", blush=False)


def _draw_bear(surf, cx, gy, s, a):
    fur = (168, 124, 90); fur_d = (142, 102, 74); fur_l = (198, 158, 124)
    out = (114, 80, 56); muzzle = (212, 180, 146); nose_c = (58, 46, 46)
    k = _quad(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
              body_w=52, body_h=34, body_lift=13, leg_w=8)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    hh = a["headbob"]
    hx, hy, hr = bcx + bw * 0.44, bcy - bh * 0.56 + hh, 18.0 * s
    et = a["ear"]
    _round_ear(surf, hx - hr * 0.74, hy - hr * 0.80 + et, hr * 0.42, fur, out, muzzle)
    _round_ear(surf, hx + hr * 0.74, hy - hr * 0.80 - et, hr * 0.42, fur, out, muzzle)
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.34, hy - hr * 0.34, hr * 0.36, hr * 0.34)
    _oell(surf, muzzle, out, hx + hr * 0.02, hy + hr * 0.30, hr * 0.62, hr * 0.5)
    pygame.draw.circle(surf, nose_c, (ri(hx), ri(hy + hr * 0.08)), max(1, ri(2.4 * s)))
    face(surf, hx, hy - hr * 0.04, hr, s, a, eye_dx=5.6, nose=False, mouth="none", blush=True, blush_c=(214, 150, 120))
    pygame.draw.line(surf, nose_c, (ri(hx), ri(hy + hr * 0.16)), (ri(hx), ri(hy + hr * 0.36)), max(1, ri(1.2 * s)))


def _draw_frog(surf, cx, gy, s, a):
    body = (138, 194, 108); body_d = (108, 164, 82); body_l = (182, 218, 150)
    out = (86, 132, 68); belly = (222, 234, 184)
    bob = a["bob"]; air = a["airborne"]
    bcx = cx
    bcy = gy - 9 * s + bob
    bw, bh = 32.0 * s, 19.0 * s
    body_bottom = bcy + bh * 0.7
    for sgn in (-1, 1):
        fx = bcx + sgn * bw * 0.42
        if air:
            pygame.draw.line(surf, body_d, (ri(fx), ri(body_bottom - 3 * s)),
                             (ri(fx + sgn * 4 * s), ri(body_bottom + 2 * s)), max(2, ri(3.2 * s)))
        else:
            for tdx in (-1.8, 0, 1.8):
                pygame.draw.circle(surf, body_d, (ri(fx + tdx * s), ri(body_bottom)), max(1, ri(1.6 * s)))
    _oell(surf, body, out, bcx, bcy, bw * 0.5, bh * 0.5)
    _under(surf, belly, bcx, bcy + bh * 0.24, bw * 0.34, bh * 0.32)
    _hi(surf, body_l, bcx - bw * 0.22, bcy - bh * 0.16, bw * 0.22, bh * 0.2)
    for sgn in (-1, 1):
        ex = bcx + sgn * bw * 0.28
        ey = bcy - bh * 0.58
        _ocirc(surf, body, out, ex, ey, 5.0 * s)
        if a["sleeping"] or a["blink"]:
            _closed_eye(surf, (ex, ey), s)
        else:
            _big_eye(surf, (ex, ey - 0.5 * s), s, (88, 130, 70))
    pygame.draw.arc(surf, out, (ri(bcx - bw * 0.34), ri(bcy - bh * 0.12), ri(bw * 0.68), ri(bh * 0.74)),
                    1.05 * math.pi, 1.95 * math.pi, max(1, ri(1.7 * s)))
    _blush(surf, bcx - bw * 0.38, bcy + bh * 0.04, s, (240, 168, 176))
    _blush(surf, bcx + bw * 0.38 - 4 * s, bcy + bh * 0.04, s, (240, 168, 176))


def _draw_bird(surf, cx, gy, s, a):
    body = (126, 178, 228); body_d = (96, 148, 206); body_l = (196, 222, 248)
    out = (92, 118, 160); belly = (248, 244, 228); beak = (246, 184, 96)
    bob = a["bob"]; air = a["airborne"]
    bcx = cx
    bcy = gy - 12 * s + bob
    bw, bh = 22.0 * s, 24.0 * s
    body_bottom = bcy + bh * 0.62
    if not air:
        for sgn in (-1, 1):
            lx = bcx + sgn * 3.5 * s
            pygame.draw.line(surf, beak, (ri(lx), ri(body_bottom - 1 * s)), (ri(lx), ri(body_bottom + 3 * s)), max(1, ri(1.5 * s)))
            pygame.draw.line(surf, beak, (ri(lx - 2 * s), ri(body_bottom + 3 * s)), (ri(lx + 2 * s), ri(body_bottom + 3 * s)), max(1, ri(1.2 * s)))
    pygame.draw.polygon(surf, body_d, [(ri(bcx - bw * 0.4), ri(bcy + bh * 0.1)),
                                       (ri(bcx - bw * 1.0), ri(bcy + bh * 0.28)),
                                       (ri(bcx - bw * 0.4), ri(bcy + bh * 0.38))])
    _oell(surf, body, out, bcx, bcy, bw * 0.5, bh * 0.5)
    _under(surf, belly, bcx + bw * 0.05, bcy + bh * 0.22, bw * 0.32, bh * 0.3)
    _hi(surf, body_l, bcx - bw * 0.2, bcy - bh * 0.2, bw * 0.24, bh * 0.24)
    flap = -3 * s if air else math.sin(a["t"] * 5) * 1.2 * s
    _oell(surf, body_d, out, bcx + bw * 0.2, bcy + flap, bw * 0.28, bh * 0.32)
    hh = a["headbob"]
    hx, hy, hr = bcx + bw * 0.14, bcy - bh * 0.46 + hh, 9.5 * s
    pygame.draw.line(surf, body_d, (ri(hx), ri(hy - hr)), (ri(hx - 1 * s), ri(hy - hr * 1.5)), max(1, ri(1.6 * s)))
    _ocirc(surf, body, out, hx, hy, hr)
    _hi(surf, body_l, hx - hr * 0.3, hy - hr * 0.3, hr * 0.3, hr * 0.3)
    pygame.draw.polygon(surf, beak, [(ri(hx + hr * 0.72), ri(hy)), (ri(hx + hr * 1.5), ri(hy + hr * 0.22)),
                                     (ri(hx + hr * 0.72), ri(hy + hr * 0.46))])
    face(surf, hx, hy, hr, s, a, eye_dx=3.8, nose=False, mouth="none", big_eyes=True,
         eye_out=(92, 118, 160), blush=True, blush_c=(236, 170, 180))


# ===========================================================================
# REMAINING SPECIES - same toolkit, same cozy bar
# ===========================================================================
def _draw_fox(surf, cx, gy, s, a):
    fur = (234, 148, 86); fur_d = (208, 122, 66); fur_l = (250, 188, 140)
    out = (150, 90, 54); white = (250, 244, 234); ear_d = (74, 58, 54); nose_c = (54, 44, 46)
    k = _quad(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
              body_w=42, body_h=20, body_lift=15, leg_w=4.4, belly=white)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    rest, lean = k["rest"], k["lean"]
    sway = math.sin(a["t"] * 4.0) * 2.4 * s
    _tail(surf, [k["rear"], (k["rear"][0] - 9 * s, k["rear"][1] + 1 * s),
                 (k["rear"][0] - 18 * s, k["rear"][1] - 4 * s + sway)],
          [5.0, 5.6, 3.6], s, fur, white, out)
    hh = a["headbob"]
    hx = bcx + bw * 0.50 + lean * 0.5
    hy = bcy - bh * (0.45 if rest else 0.74) + hh
    hr = 13.0 * s
    et = a["ear"]
    _ear_tri(surf, (hx - hr * 0.88, hy - hr * 0.35 + et), (hx - hr * 0.12, hy - hr * 0.5),
             (hx - hr * 0.62, hy - hr * 1.55), fur, out, ear_d)
    _ear_tri(surf, (hx + hr * 0.12, hy - hr * 0.5), (hx + hr * 0.88, hy - hr * 0.35 - et),
             (hx + hr * 0.62, hy - hr * 1.55), fur, out, ear_d)
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.32, hy - hr * 0.3, hr * 0.3, hr * 0.3)
    # white cheek + a forward-pointing snout (nose integrated at the tip)
    _oell(surf, white, out, hx - hr * 0.38, hy + hr * 0.5, hr * 0.36, hr * 0.32)
    tx, ty = hx + hr * 1.22, hy + hr * 0.30
    tb = (hx - hr * 0.12, hy - hr * 0.08); bb = (hx - hr * 0.02, hy + hr * 0.64)
    _pg(surf, out, [(tb[0] - 1 * s, tb[1] - 1 * s), (tx + 1 * s, ty), (bb[0] - 1 * s, bb[1] + 1 * s)])
    _pg(surf, white, [tb, (tx, ty), bb])
    _pg(surf, fur, [tb, (tx, ty), (hx + hr * 0.18, hy + hr * 0.16)])
    pygame.draw.circle(surf, out, (ri(tx), ri(ty)), max(2, ri(2.5 * s)))
    pygame.draw.circle(surf, nose_c, (ri(tx), ri(ty)), max(1, ri(2.0 * s)))
    surf.set_at((clamp(ri(tx - 1), 0, surf.get_width() - 1), clamp(ri(ty - 1), 0, surf.get_height() - 1)), (128, 118, 118))
    pygame.draw.line(surf, out, (ri(tx - hr * 0.04), ri(ty + hr * 0.18)), (ri(hx + hr * 0.52), ri(ty + hr * 0.34)), max(1, ri(1 * s)))
    face(surf, hx - hr * 0.04, hy - hr * 0.16, hr, s, a, eye_dx=4.4, eye_dy=-1.0, nose=False, mouth="none",
         blush=True, blush_c=(246, 170, 150))


def _draw_raccoon(surf, cx, gy, s, a):
    fur = (172, 176, 186); fur_d = (142, 146, 158); fur_l = (210, 212, 220)
    out = (96, 98, 110); mask = (64, 62, 72); pale = (228, 230, 236); ring = (92, 94, 106)
    k = _quad(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
              body_w=42, body_h=21, body_lift=15, leg_w=4.6, belly=fur_l)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    rest, lean = k["rest"], k["lean"]
    tx, ty = k["rear"]
    sway = math.sin(a["t"] * 4) * 1.5 * s
    for i in range(4):
        c = ring if i % 2 else mask
        _ocirc(surf, c, out, tx - (5 + i * 6) * s, ty + (4 - i * 0.5) * s + (sway if i > 1 else 0), (5.4 - i * 0.7) * s)
    hh = a["headbob"]
    hx = bcx + bw * 0.50 + lean * 0.5
    hy = bcy - bh * (0.45 if rest else 0.72) + hh
    hr = 13.0 * s
    et = a["ear"]
    _ear_tri(surf, (hx - hr * 0.85, hy - hr * 0.4 + et), (hx - hr * 0.2, hy - hr * 0.55),
             (hx - hr * 0.6, hy - hr * 1.25), fur, out, pale)
    _ear_tri(surf, (hx + hr * 0.2, hy - hr * 0.55), (hx + hr * 0.85, hy - hr * 0.4 - et),
             (hx + hr * 0.6, hy - hr * 1.25), fur, out, pale)
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.34, hy - hr * 0.36, hr * 0.3, hr * 0.3)
    _oell(surf, pale, out, hx + hr * 0.04, hy + hr * 0.14, hr * 0.74, hr * 0.82)
    _oell(surf, pale, out, hx + hr * 0.06, hy + hr * 0.52, hr * 0.4, hr * 0.34)
    pygame.draw.ellipse(surf, mask, (ri(hx - hr * 0.78), ri(hy - hr * 0.2), ri(hr * 0.78), ri(hr * 0.5)))
    pygame.draw.ellipse(surf, mask, (ri(hx + hr * 0.0), ri(hy - hr * 0.2), ri(hr * 0.78), ri(hr * 0.5)))
    _pg(surf, mask, [(hx - hr * 0.18, hy - hr * 0.18), (hx + hr * 0.18, hy - hr * 0.18), (hx, hy + hr * 0.22)])
    for sgn in (-1, 1):
        ex, ey = hx + sgn * hr * 0.4, hy - hr * 0.16
        if a["sleeping"] or a["blink"]:
            _closed_eye(surf, (ex, ey), s, pale)
        else:
            pygame.draw.circle(surf, pale, (ri(ex), ri(ey)), max(1, ri(2.3 * s)))
            pygame.draw.circle(surf, (40, 36, 42), (ri(ex), ri(ey)), max(1, ri(1.5 * s)))
            surf.set_at((clamp(ri(ex - 1), 0, surf.get_width() - 1), clamp(ri(ey - 1), 0, surf.get_height() - 1)), WHITE)
    pygame.draw.circle(surf, (42, 36, 40), (ri(hx + hr * 0.06), ri(hy + hr * 0.42)), max(1, ri(1.9 * s)))
    pygame.draw.arc(surf, (70, 60, 62), (ri(hx - hr * 0.2), ri(hy + hr * 0.5), ri(hr * 0.52), ri(hr * 0.4)),
                    1.15 * math.pi, 1.85 * math.pi, max(1, ri(1.1 * s)))
    if a["mood"] != "angry":
        _blush(surf, hx - hr * 0.72, hy + hr * 0.26, s, (228, 168, 168))
        _blush(surf, hx + hr * 0.72 - 4 * s, hy + hr * 0.26, s, (228, 168, 168))


def _draw_squirrel(surf, cx, gy, s, a):
    fur = (196, 134, 86); fur_d = (166, 108, 68); fur_l = (224, 170, 124)
    out = (130, 86, 52); belly = (244, 226, 200); nut = (170, 122, 70); ear_in = (226, 176, 182)
    bob = a["bob"]; rest = a["rest"]
    bcx = cx
    bcy = gy - (9 if rest else 15) * s + bob
    bw, bh = 23.0 * s, 25.0 * s
    if rest:
        bw *= 1.16; bh *= 0.84
    body_bottom = bcy + bh * 0.66
    sway = math.sin(a["t"] * 3.5) * 2.4 * s
    _tail(surf, [(bcx - bw * 0.3, body_bottom), (bcx - bw * 0.75, bcy + bh * 0.1),
                 (bcx - bw * 0.55, bcy - bh * 0.6), (bcx + bw * 0.05, bcy - bh * 1.0 + sway)],
          [4.2, 6.0, 6.2, 4.4], s, fur, fur_l, out)
    _oell(surf, fur, out, bcx, bcy, bw * 0.5, bh * 0.5)
    _under(surf, belly, bcx + bw * 0.06, bcy + bh * 0.18, bw * 0.32, bh * 0.34)
    _hi(surf, fur_l, bcx - bw * 0.2, bcy - bh * 0.2, bw * 0.22, bh * 0.22)
    if not rest:
        pygame.draw.circle(surf, fur_d, (ri(bcx + bw * 0.34), ri(bcy + bh * 0.22)), max(1, ri(2.4 * s)))
        pygame.draw.circle(surf, nut, (ri(bcx + bw * 0.52), ri(bcy + bh * 0.14)), max(1, ri(2.8 * s)))
    hh = a["headbob"]
    hx, hy, hr = bcx + bw * 0.18, bcy - bh * (0.3 if rest else 0.48) + hh, 10.0 * s
    et = a["ear"]
    _ear_tri(surf, (hx - hr * 0.7, hy - hr * 0.5 + et), (hx - hr * 0.1, hy - hr * 0.62),
             (hx - hr * 0.5, hy - hr * 1.25), fur, out, ear_in)
    _ear_tri(surf, (hx + hr * 0.1, hy - hr * 0.62), (hx + hr * 0.7, hy - hr * 0.5 - et),
             (hx + hr * 0.5, hy - hr * 1.25), fur, out, ear_in)
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.3, hy - hr * 0.3, hr * 0.3, hr * 0.3)
    face(surf, hx, hy, hr, s, a, eye_dx=4.0, nose_c=(70, 54, 54), nose_dy=4.0, mouth="none")


def _draw_turtle(surf, cx, gy, s, a):
    shell = (150, 124, 80); shell_d = (122, 98, 60); shell_l = (182, 154, 104)
    out = (96, 76, 48); skin = (150, 196, 124); skin_d = (120, 168, 100); skin_l = (184, 216, 158)
    bob = a["bob"]
    bcx = cx
    bcy = gy - 9 * s + bob
    sw, sh = 38.0 * s, 22.0 * s
    foot_y = gy - 2 * s
    step = a["step"]
    for lx, sg in ((bcx - sw * 0.34, -1), (bcx + sw * 0.3, 1), (bcx - sw * 0.12, 1), (bcx + sw * 0.12, -1)):
        fy = foot_y - (max(0.0, step * sg) * 1.5 * s if a["moving"] else 0.0)
        _oell(surf, skin, out, lx, fy, 3.6 * s, 2.6 * s)
    pygame.draw.circle(surf, skin_d, (ri(bcx - sw * 0.5), ri(bcy + sh * 0.1)), max(1, ri(2 * s)))
    hh = a["headbob"] * 0.5
    hx = bcx + sw * (0.4 if a["sleeping"] else 0.54)
    hy = bcy + sh * 0.02 + hh
    hr = 6.2 * s
    pygame.draw.line(surf, skin, (ri(bcx + sw * 0.3), ri(bcy)), (ri(hx), ri(hy)), max(3, ri(6 * s)))
    _ocirc(surf, skin, out, hx, hy, hr)
    _hi(surf, skin_l, hx - 1.6 * s, hy - 1.6 * s, 2 * s, 1.8 * s)
    if a["sleeping"] or a["blink"]:
        _closed_eye(surf, (hx + 1.2 * s, hy - 1 * s), s)
    else:
        _dot_eye(surf, (hx + 1.2 * s, hy - 1.2 * s), s)
        _dot_eye(surf, (hx - 1.8 * s, hy - 1.2 * s), s)
    _blush(surf, hx + hr * 0.2, hy + hr * 0.4, s, (236, 170, 160))
    pygame.draw.arc(surf, out, (ri(hx - 1.4 * s), ri(hy + 0.8 * s), ri(4.4 * s), ri(3 * s)),
                    1.1 * math.pi, 1.9 * math.pi, max(1, ri(1 * s)))
    _oell(surf, shell, out, bcx, bcy, sw * 0.5, sh * 0.62)
    _hi(surf, shell_l, bcx - sw * 0.18, bcy - sh * 0.3, sw * 0.22, sh * 0.24)
    _ringc(surf, shell_d, bcx, bcy - sh * 0.04, 5 * s, 1.4 * s)
    for ang in range(0, 360, 60):
        a2 = math.radians(ang)
        pygame.draw.line(surf, shell_d,
                         (ri(bcx + math.cos(a2) * sw * 0.16), ri(bcy - sh * 0.04 + math.sin(a2) * sh * 0.16)),
                         (ri(bcx + math.cos(a2) * sw * 0.42), ri(bcy - sh * 0.04 + math.sin(a2) * sh * 0.42)),
                         max(1, ri(1 * s)))


def _draw_pig(surf, cx, gy, s, a):
    fur = (246, 186, 192); fur_d = (226, 158, 168); fur_l = (255, 212, 216)
    out = (192, 124, 134); snout = (238, 162, 172); hoof = (120, 84, 88)
    k = _quad(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
              body_w=48, body_h=27, body_lift=14, leg_w=6, belly=fur_l)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    rest, lean = k["rest"], k["lean"]
    if not rest:
        pygame.draw.arc(surf, out, (ri(k["rear"][0] - 8 * s), ri(k["rear"][1] - 5 * s), ri(8 * s), ri(8 * s)),
                        0.0, 1.6 * math.pi, max(1, ri(1.6 * s)))
    hh = a["headbob"]
    hx = bcx + bw * 0.50 + lean * 0.5
    hy = bcy - bh * (0.4 if rest else 0.55) + hh
    hr = 14.0 * s
    et = a["ear"]
    _ear_tri(surf, (hx - hr * 0.72, hy - hr * 0.62 + et), (hx - hr * 0.05, hy - hr * 0.72),
             (hx - hr * 0.5, hy - hr * 1.3), fur_d, out)
    _ear_tri(surf, (hx + hr * 0.05, hy - hr * 0.72), (hx + hr * 0.72, hy - hr * 0.62 - et),
             (hx + hr * 0.5, hy - hr * 1.3), fur_d, out)
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.32, hy - hr * 0.32, hr * 0.32, hr * 0.3)
    _oell(surf, snout, out, hx + hr * 0.12, hy + hr * 0.42, hr * 0.58, hr * 0.44)
    pygame.draw.circle(surf, out, (ri(hx - hr * 0.05), ri(hy + hr * 0.42)), max(1, ri(1.5 * s)))
    pygame.draw.circle(surf, out, (ri(hx + hr * 0.28), ri(hy + hr * 0.42)), max(1, ri(1.5 * s)))
    face(surf, hx, hy, hr, s, a, eye_dx=5.0, nose=False, mouth="none")
    if not rest:
        for fx in (bcx + bw * 0.27, bcx - bw * 0.30):
            pygame.draw.circle(surf, hoof, (ri(fx), ri(gy - 1 * s)), max(1, ri(1.8 * s)))


def _draw_goat(surf, cx, gy, s, a):
    fur = (240, 236, 228); fur_d = (212, 206, 196); fur_l = (255, 254, 250)
    out = (168, 156, 146); horn = (150, 118, 84); horn_d = (120, 92, 62)
    beard = (224, 220, 212); muz = (224, 214, 204)
    hh = a["headbob"]; rest = a["rest"]; lean = a["lean"] * s
    k = _ungulate(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
                  body_w=42, body_h=21, body_lift=19, leg_w=4.2, stride=3.0, lift=3.2,
                  sock=fur_d, hoof=(78, 64, 54), hoofed=True)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    if not rest:
        pygame.draw.line(surf, out, (ri(k["rump"][0]), ri(k["rump"][1])),
                         (ri(k["rump"][0] - 2 * s), ri(k["rump"][1] - 6 * s)), max(2, ri(2.4 * s)))
    hx = bcx + bw * 0.66 + lean * 0.5
    hy = bcy - bh * (0.34 if rest else 0.78) + hh
    hr = 11.0 * s
    _pg(surf, out, [(bcx + bw * 0.32, bcy - bh * 0.42), (hx - hr * 0.4, hy - hr * 0.1),
                    (hx - hr * 0.05, hy + hr * 0.7), (bcx + bw * 0.44, bcy - bh * 0.02)])
    _pg(surf, fur, [(bcx + bw * 0.35, bcy - bh * 0.38), (hx - hr * 0.32, hy - hr * 0.05),
                    (hx - hr * 0.05, hy + hr * 0.62), (bcx + bw * 0.42, bcy - bh * 0.05)])
    et = a["ear"]
    for sgn in (-1, 1):
        pygame.draw.line(surf, horn, (ri(hx + sgn * hr * 0.3), ri(hy - hr * 0.78)),
                         (ri(hx + sgn * hr * 0.5), ri(hy - hr * 1.5)), max(2, ri(2.6 * s)))
        pygame.draw.line(surf, horn_d, (ri(hx + sgn * hr * 0.5), ri(hy - hr * 1.5)),
                         (ri(hx + sgn * hr * 0.78), ri(hy - hr * 1.78)), max(1, ri(2 * s)))
    _drop_ear(surf, hx - hr * 0.98, hy - hr * 0.05 + et, hr * 0.56, hr * 0.3, fur_d, out)
    _drop_ear(surf, hx + hr * 0.98, hy - hr * 0.05 - et, hr * 0.56, hr * 0.3, fur_d, out)
    _oell(surf, fur, out, hx, hy, hr * 0.78, hr * 0.98)
    _oell(surf, muz, out, hx + hr * 0.18, hy + hr * 0.62, hr * 0.46, hr * 0.4)
    _hi(surf, fur_l, hx - hr * 0.28, hy - hr * 0.32, hr * 0.3, hr * 0.3)
    pygame.draw.circle(surf, (120, 104, 96), (ri(hx + hr * 0.28), ri(hy + hr * 0.6)), max(1, ri(1.4 * s)))
    face(surf, hx - hr * 0.04, hy - hr * 0.04, hr, s, a, eye_dx=3.8, nose=False, mouth="none", blush=True, blush_c=(228, 198, 184))
    _pg(surf, beard, [(hx - 2 * s, hy + hr * 0.92), (hx + 2 * s, hy + hr * 0.92), (hx, hy + hr * 1.5)])


def _draw_chicken(surf, cx, gy, s, a):
    body = (252, 248, 242); body_d = (226, 220, 212); body_l = (255, 255, 254)
    out = (190, 178, 168); comb = (238, 98, 98); beak = (246, 190, 92); wattle = (226, 82, 82)
    bob = a["bob"]; air = a["airborne"]; rest = a["rest"]
    bcx = cx
    bcy = gy - (10 if rest else 14) * s + bob
    bw, bh = 24.0 * s, 26.0 * s
    body_bottom = bcy + bh * 0.62
    if not air and not rest:
        for sgn in (-1, 1):
            lx = bcx + sgn * 3.5 * s
            pygame.draw.line(surf, beak, (ri(lx), ri(body_bottom)), (ri(lx), ri(body_bottom + 3 * s)), max(1, ri(1.5 * s)))
            pygame.draw.line(surf, beak, (ri(lx - 2 * s), ri(body_bottom + 3 * s)), (ri(lx + 2 * s), ri(body_bottom + 3 * s)), max(1, ri(1.2 * s)))
    pygame.draw.polygon(surf, body_d, [(ri(bcx - bw * 0.4), ri(bcy)), (ri(bcx - bw * 1.0), ri(bcy - bh * 0.25)),
                                       (ri(bcx - bw * 0.5), ri(bcy + bh * 0.3))])
    _oell(surf, body, out, bcx, bcy, bw * 0.5, bh * 0.5)
    _hi(surf, body_l, bcx - bw * 0.2, bcy - bh * 0.2, bw * 0.24, bh * 0.24)
    flap = -2 * s if air else math.sin(a["t"] * 5) * 1.0 * s
    _oell(surf, body_d, out, bcx + bw * 0.18, bcy + bh * 0.05 + flap, bw * 0.26, bh * 0.28)
    hh = a["headbob"]
    hx, hy, hr = bcx + bw * 0.2, bcy - bh * 0.48 + hh, 9.5 * s
    for dxx in (-0.3, 0.0, 0.3):
        pygame.draw.circle(surf, comb, (ri(hx + dxx * hr), ri(hy - hr * 1.05)), max(1, ri(2.2 * s)))
    _ocirc(surf, body, out, hx, hy, hr)
    _hi(surf, body_l, hx - hr * 0.3, hy - hr * 0.3, hr * 0.3, hr * 0.3)
    pygame.draw.polygon(surf, beak, [(ri(hx + hr * 0.7), ri(hy + hr * 0.02)), (ri(hx + hr * 1.5), ri(hy + hr * 0.28)),
                                     (ri(hx + hr * 0.7), ri(hy + hr * 0.5))])
    pygame.draw.circle(surf, wattle, (ri(hx + hr * 0.74), ri(hy + hr * 0.6)), max(1, ri(1.7 * s)))
    face(surf, hx, hy, hr, s, a, eye_dx=3.6, nose=False, mouth="none", blush=True, blush_c=(244, 180, 180))


def _draw_duck(surf, cx, gy, s, a):
    body = (250, 246, 238); body_d = (224, 218, 208); body_l = (255, 255, 253)
    out = (188, 176, 166); bill = (246, 190, 92)
    bob = a["bob"]
    bcx = cx
    bcy = gy - 12 * s + bob
    bw, bh = 28.0 * s, 20.0 * s
    pygame.draw.polygon(surf, body_d, [(ri(bcx - bw * 0.4), ri(bcy)), (ri(bcx - bw * 0.8), ri(bcy - bh * 0.22)),
                                       (ri(bcx - bw * 0.42), ri(bcy + bh * 0.2))])
    _oell(surf, body, out, bcx, bcy, bw * 0.5, bh * 0.55)
    _hi(surf, body_l, bcx - bw * 0.2, bcy - bh * 0.2, bw * 0.24, bh * 0.24)
    _oell(surf, body_d, out, bcx + bw * 0.12, bcy + bh * 0.05, bw * 0.24, bh * 0.3)
    hh = a["headbob"]
    hx, hy, hr = bcx + bw * 0.4, bcy - bh * 0.74 + hh, 9.5 * s
    pygame.draw.line(surf, body, (ri(bcx + bw * 0.3), ri(bcy - bh * 0.3)), (ri(hx), ri(hy + hr * 0.4)), max(3, ri(7 * s)))
    _ocirc(surf, body, out, hx, hy, hr)
    _hi(surf, body_l, hx - hr * 0.3, hy - hr * 0.3, hr * 0.3, hr * 0.3)
    _oell(surf, bill, out, hx + hr * 1.0, hy + hr * 0.22, hr * 0.6, hr * 0.34)
    face(surf, hx - hr * 0.1, hy, hr, s, a, eye_dx=3.4, nose=False, mouth="none", big_eyes=True,
         eye_out=(120, 110, 96), blush=True, blush_c=(244, 184, 150))


def _draw_monkey(surf, cx, gy, s, a):
    fur = (156, 118, 84); fur_d = (130, 96, 68); fur_l = (188, 152, 118)
    out = (104, 76, 52); face_c = (228, 192, 154); face_l = (244, 214, 182); sole = (224, 188, 150)
    bob = a["bob"]; rest = a["rest"]
    bcx = cx
    bcy = gy - (9 if rest else 14) * s + bob
    bw, bh = 24.0 * s, 23.0 * s
    if rest:
        bw *= 1.14; bh *= 0.84
    body_bottom = bcy + bh * 0.6
    sway = math.sin(a["t"] * 3.0) * 2.2 * s
    _tail(surf, [(bcx - bw * 0.42, bcy + bh * 0.28), (bcx - bw * 0.78, bcy + bh * 0.1),
                 (bcx - bw * 0.7, bcy - bh * 0.4), (bcx - bw * 0.3, bcy - bh * 0.62 + sway)],
          [2.6, 2.4, 2.2, 2.0], s, fur, fur_l, out)
    if not rest:
        for sgn in (-1, 1):
            _oell(surf, fur, out, bcx + sgn * bw * 0.26, body_bottom, 3.2 * s, 2.2 * s)
        for sgn in (-1, 1):
            _oell(surf, sole, out, bcx + sgn * bw * 0.26, body_bottom + 0.6 * s, 1.8 * s, 1.2 * s)
    _oell(surf, fur, out, bcx, bcy, bw * 0.5, bh * 0.5)
    _oell(surf, face_l, out, bcx, bcy + bh * 0.16, bw * 0.32, bh * 0.32)
    _hi(surf, fur_l, bcx - bw * 0.2, bcy - bh * 0.2, bw * 0.22, bh * 0.22)
    wave = abs(math.sin(a["t"] * 7)) * 0.5 if a["mood"] == "happy" else 0.0
    pygame.draw.line(surf, fur, (ri(bcx - bw * 0.32), ri(bcy - bh * 0.1)),
                     (ri(bcx - bw * 0.1), ri(bcy + bh * 0.28)), max(2, ri(3.4 * s)))
    pygame.draw.circle(surf, fur_d, (ri(bcx - bw * 0.08), ri(bcy + bh * 0.3)), max(1, ri(2.2 * s)))
    pygame.draw.line(surf, fur, (ri(bcx + bw * 0.32), ri(bcy - bh * 0.05)),
                     (ri(bcx + bw * 0.5), ri(bcy - bh * (0.4 + wave))), max(2, ri(3.4 * s)))
    pygame.draw.circle(surf, fur_d, (ri(bcx + bw * 0.52), ri(bcy - bh * (0.46 + wave))), max(1, ri(2.2 * s)))
    hh = a["headbob"]
    hx, hy, hr = bcx + bw * 0.04, bcy - bh * (0.4 if rest else 0.62) + hh, 12.5 * s
    et = a["ear"]
    _round_ear(surf, hx - hr * 0.92, hy + hr * 0.05 + et, hr * 0.4, fur, out, face_c)
    _round_ear(surf, hx + hr * 0.92, hy + hr * 0.05 - et, hr * 0.4, fur, out, face_c)
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.3, hy - hr * 0.34, hr * 0.3, hr * 0.28)
    _oell(surf, face_c, out, hx, hy + hr * 0.12, hr * 0.72, hr * 0.82)
    _oell(surf, face_c, out, hx, hy + hr * 0.5, hr * 0.46, hr * 0.4)
    face(surf, hx, hy + hr * 0.04, hr, s, a, eye_dx=3.4, nose_c=(118, 88, 68), nose_dy=3.4,
         mouth="smile", mouth_w=2.6, blush=True, blush_c=(234, 176, 152))


def _draw_horse(surf, cx, gy, s, a):
    fur = (182, 128, 84); fur_d = (152, 104, 66); fur_l = (212, 164, 118); out = (112, 76, 48)
    mane = (86, 56, 38); mane_l = (120, 82, 52); muz = (140, 100, 74); nose_c = (52, 42, 44)
    hoof = (56, 48, 46)
    hh = a["headbob"]; rest = a["rest"]; lean = a["lean"] * s
    bcx0 = cx + lean * 0.5
    bcy0 = gy - (23 * 0.42 if rest else 23) * s + a["bob"]
    sway = math.sin(a["t"] * 3.0) * 2.4 * s
    tlx, tly = bcx0 - 22 * s, bcy0 - 6 * s
    _tail(surf, [(tlx, tly), (tlx - 2 * s, tly + 8 * s),
                 (tlx + 1 * s, tly + 18 * s + sway * 0.5), (tlx - 2 * s, tly + 28 * s + sway)],
          [4.6, 4.4, 3.6, 2.6], s, mane, mane_l, out)
    k = _ungulate(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
                  body_w=46, body_h=24, body_lift=23, leg_w=6, stride=3.0, lift=3.2,
                  sock=fur_d, hoof=hoof, belly=fur_l, hoofed=True)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    # head set FORWARD and only a little above the back (no llama neck)
    u = 8.0 * s
    hx = bcx + bw * 0.74 + lean * 0.5
    hy = bcy - bh * (0.2 if rest else 0.92) + hh
    A = (hx - u * 0.7, hy - u * 0.5); G = (hx - u * 0.4, hy + u * 1.0)
    W = (bcx + bw * 0.14, bcy - bh * 0.5); Cf = (bcx + bw * 0.5, bcy - bh * 0.02)
    # thick neck angled forward from withers/chest up to the head
    _pg(surf, out, [A, W, Cf, G])
    _pg(surf, fur, [(A[0] + 0.6 * s, A[1] + 0.8 * s), (W[0] + 1.6 * s, W[1] + 1 * s),
                    (Cf[0] - 1 * s, Cf[1] - 1 * s), (G[0] + 0.6 * s, G[1] - 0.6 * s)])
    # head: an elongated wedge pointing down-forward (the horse cue)
    H = [(hx - u * 0.7, hy - u * 0.5), (hx + u * 0.3, hy - u * 0.85), (hx + u * 1.1, hy - u * 0.1),
         (hx + u * 1.5, hy + u * 0.7), (hx + u * 1.35, hy + u * 1.4), (hx + u * 0.65, hy + u * 1.5),
         (hx - u * 0.4, hy + u * 1.0), (hx - u * 0.85, hy + u * 0.1)]
    _pg(surf, out, H)
    cxx = sum(p[0] for p in H) / len(H); cyy = sum(p[1] for p in H) / len(H)
    _pg(surf, fur, [(lerp(p[0], cxx, 0.1), lerp(p[1], cyy, 0.1)) for p in H])
    _oell(surf, muz, out, hx + u * 1.18, hy + u * 1.0, u * 0.5, u * 0.52)
    pygame.draw.circle(surf, nose_c, (ri(hx + u * 1.28), ri(hy + u * 0.82)), max(1, ri(1.5 * s)))
    pygame.draw.line(surf, out, (ri(hx + u * 1.02), ri(hy + u * 1.32)), (ri(hx + u * 1.4), ri(hy + u * 1.18)), max(1, ri(1 * s)))
    _hi(surf, fur_l, hx + u * 0.15, hy - u * 0.4, u * 0.32, u * 0.34)
    et = a["ear"]
    _ear_tri(surf, (hx - u * 0.7, hy - u * 0.45 + et), (hx - u * 0.1, hy - u * 0.7), (hx - u * 0.5, hy - u * 1.6), fur, out, muz)
    _ear_tri(surf, (hx + u * 0.12, hy - u * 0.78), (hx + u * 0.6, hy - u * 0.55 - et), (hx + u * 0.36, hy - u * 1.5), fur, out, muz)
    for dx in (-0.2, 0.12, 0.42):
        pygame.draw.line(surf, mane, (ri(hx + dx * u), ri(hy - u * 0.62)), (ri(hx + dx * u + 1.2 * s), ri(hy - u * 0.02)), max(1, ri(2 * s)))
    for i in range(7):
        f = i / 6.0
        mx = lerp(A[0], W[0], f); my = lerp(A[1], W[1], f)
        pygame.draw.line(surf, (mane if i % 2 else mane_l), (ri(mx), ri(my)), (ri(mx - 3.4 * s), ri(my + 6.5 * s)), max(2, ri(3 * s)))
    if a["sleeping"] or a["blink"]:
        _closed_eye(surf, (hx + u * 0.18, hy - u * 0.02), s)
    else:
        ex, ey = ri(hx + u * 0.18), ri(hy - u * 0.02)
        pygame.draw.circle(surf, out, (ex, ey), max(2, ri(2.6 * s)))
        pygame.draw.circle(surf, (44, 38, 44), (ex, ey), max(1, ri(2 * s)))
        surf.set_at((clamp(ex - 1, 0, surf.get_width() - 1), clamp(ey - 1, 0, surf.get_height() - 1)), WHITE)
    if a["mood"] != "angry":
        _blush(surf, hx - u * 0.05, hy + u * 0.4, s, (204, 146, 120))


def _draw_owl(surf, cx, gy, s, a):
    fur = (182, 146, 106); fur_d = (154, 120, 86); fur_l = (210, 178, 140)
    out = (118, 88, 60); belly = (226, 204, 170); beak = (242, 182, 98); disc = (238, 222, 192)
    bob = a["bob"]; rest = a["rest"]
    bcx = cx
    bcy = gy - (11 if rest else 14) * s + bob
    bw, bh = 26.0 * s, 28.0 * s
    body_bottom = bcy + bh * 0.6
    if not rest:
        for sgn in (-1, 1):
            lx = bcx + sgn * 3.5 * s
            pygame.draw.line(surf, beak, (ri(lx), ri(body_bottom)), (ri(lx), ri(body_bottom + 2.5 * s)), max(1, ri(1.5 * s)))
    _oell(surf, fur, out, bcx, bcy, bw * 0.5, bh * 0.5)
    _under(surf, belly, bcx, bcy + bh * 0.16, bw * 0.34, bh * 0.34)
    flap = -3 * s if a["airborne"] else 0.0
    _oell(surf, fur_d, out, bcx - bw * 0.34, bcy + bh * 0.04 + flap, bw * 0.16, bh * 0.4)
    _oell(surf, fur_d, out, bcx + bw * 0.34, bcy + bh * 0.04 + flap, bw * 0.16, bh * 0.4)
    _hi(surf, fur_l, bcx - bw * 0.18, bcy - bh * 0.22, bw * 0.2, bh * 0.2)
    et = a["ear"]
    _ear_tri(surf, (bcx - bw * 0.4, bcy - bh * 0.4), (bcx - bw * 0.12, bcy - bh * 0.45),
             (bcx - bw * 0.34, bcy - bh * 0.78 + et), fur, out)
    _ear_tri(surf, (bcx + bw * 0.12, bcy - bh * 0.45), (bcx + bw * 0.4, bcy - bh * 0.4),
             (bcx + bw * 0.34, bcy - bh * 0.78 - et), fur, out)
    for sgn in (-1, 1):
        ex = bcx + sgn * bw * 0.22
        ey = bcy - bh * 0.22
        pygame.draw.circle(surf, disc, (ri(ex), ri(ey)), max(2, ri(5.4 * s)))
        if a["sleeping"] or a["blink"]:
            _closed_eye(surf, (ex, ey), s)
        else:
            _big_eye(surf, (ex, ey), s, (118, 88, 60))
    pygame.draw.polygon(surf, beak, [(ri(bcx), ri(bcy - bh * 0.08)), (ri(bcx - 2 * s), ri(bcy)),
                                     (ri(bcx + 2 * s), ri(bcy))])


def _draw_hedgehog(surf, cx, gy, s, a):
    spike = (136, 108, 78); spike_d = (106, 82, 58); spike_l = (160, 132, 100)
    out = (92, 70, 48); face_c = (226, 198, 164); face_l = (242, 218, 188); nose_c = (72, 56, 54)
    bob = a["bob"]
    bcx = cx
    bcy = gy - 9 * s + bob
    bw, bh = 36.0 * s, 22.0 * s
    body_bottom = bcy + bh * 0.6
    if not a["rest"]:
        for lx in (bcx - bw * 0.2, bcx + bw * 0.05):
            _oell(surf, face_c, out, lx, body_bottom, 2.8 * s, 2 * s)
    pygame.draw.ellipse(surf, out, (ri(bcx - bw * 0.5) - 1, ri(bcy - bh * 0.5) - 1, ri(bw) + 2, ri(bh) + 2))
    pygame.draw.ellipse(surf, spike, (ri(bcx - bw * 0.5), ri(bcy - bh * 0.5), ri(bw), ri(bh)))
    for i in range(12):
        f = i / 11.0
        sx = lerp(bcx - bw * 0.46, bcx + bw * 0.36, f)
        sy = bcy - bh * 0.42 - math.sin(f * math.pi) * bh * 0.18
        c = spike_l if i % 2 else spike_d
        pygame.draw.line(surf, c, (ri(sx), ri(sy)), (ri(sx - 2 * s), ri(sy - 4.5 * s)), max(1, ri(1.7 * s)))
    _hi(surf, spike_l, bcx - bw * 0.2, bcy - bh * 0.28, bw * 0.16, bh * 0.18)
    hh = a["headbob"] * 0.4
    hx, hy = bcx + bw * 0.44, bcy + bh * 0.16 + hh
    _oell(surf, face_c, out, hx, hy, 7.4 * s, 6.4 * s)
    _hi(surf, face_l, hx - 2 * s, hy - 2 * s, 2.2 * s, 1.8 * s)
    pygame.draw.circle(surf, nose_c, (ri(hx + 5.8 * s), ri(hy + 0.5 * s)), max(1, ri(1.7 * s)))
    if a["sleeping"] or a["blink"]:
        _closed_eye(surf, (hx + 0.5 * s, hy - 1 * s), s)
    else:
        _dot_eye(surf, (hx + 0.5 * s, hy - 1 * s), s)
    _blush(surf, hx - 1 * s, hy + 1.6 * s, s, (240, 176, 184))


def _draw_tanuki(surf, cx, gy, s, a):
    fur = (166, 140, 112); fur_d = (136, 112, 88); fur_l = (194, 170, 142)
    out = (104, 84, 62); mask = (72, 64, 62); pale = (230, 222, 210); dark = (58, 50, 50)
    k = _quad(surf, cx, gy, s, fur, fur_d, fur_l, out, a,
              body_w=44, body_h=24, body_lift=14, leg_w=6, belly=pale)
    bcx, bcy, bw, bh = k["bcx"], k["bcy"], k["bw"], k["bh"]
    rest, lean = k["rest"], k["lean"]
    sway = math.sin(a["t"] * 3.5) * 2 * s
    _tail(surf, [k["rear"], (k["rear"][0] - 8 * s, k["rear"][1] + 2 * s),
                 (k["rear"][0] - 15 * s, k["rear"][1] - 2 * s + sway)], [5.0, 5.2, 3.4], s, fur, dark, out)
    hh = a["headbob"]
    hx = bcx + bw * 0.48 + lean * 0.5
    hy = bcy - bh * (0.42 if rest else 0.58) + hh
    hr = 13.0 * s
    et = a["ear"]
    _ear_tri(surf, (hx - hr * 0.8, hy - hr * 0.4 + et), (hx - hr * 0.2, hy - hr * 0.55),
             (hx - hr * 0.55, hy - hr * 1.15), fur_d, out, pale)
    _ear_tri(surf, (hx + hr * 0.2, hy - hr * 0.55), (hx + hr * 0.8, hy - hr * 0.4 - et),
             (hx + hr * 0.55, hy - hr * 1.15), fur_d, out, pale)
    _ocirc(surf, fur, out, hx, hy, hr)
    _hi(surf, fur_l, hx - hr * 0.32, hy - hr * 0.32, hr * 0.3, hr * 0.3)
    _oell(surf, pale, out, hx + hr * 0.05, hy + hr * 0.32, hr * 0.52, hr * 0.44)
    pygame.draw.circle(surf, mask, (ri(hx - hr * 0.42), ri(hy + hr * 0.05)), max(1, ri(hr * 0.36)))
    pygame.draw.circle(surf, mask, (ri(hx + hr * 0.42), ri(hy + hr * 0.05)), max(1, ri(hr * 0.36)))
    _dot_eye(surf, (hx - hr * 0.42, hy), s, WHITE)
    _dot_eye(surf, (hx + hr * 0.42, hy), s, WHITE)
    pygame.draw.circle(surf, dark, (ri(hx + hr * 0.02), ri(hy + hr * 0.2)), max(1, ri(1.9 * s)))


def _draw_butterfly(surf, cx, gy, s, a):
    wing = (238, 162, 100); wing_d = (210, 128, 72); wing_l = (250, 198, 152)
    out = (150, 92, 56); body_c = (90, 74, 70); spot = (255, 234, 198)
    bob = a["bob"]
    ccx = cx
    ccy = gy - 18 * s + bob
    flap = abs(math.sin(a["t"] * 7.0))
    wsp = 0.45 + 0.55 * flap
    for sgn in (-1, 1):
        _oell(surf, wing, out, ccx + sgn * 9 * s * wsp, ccy - 5 * s, 7 * s * wsp, 8 * s)
        _oell(surf, wing_d, out, ccx + sgn * 8 * s * wsp, ccy + 5 * s, 6 * s * wsp, 6 * s)
        pygame.draw.circle(surf, spot, (ri(ccx + sgn * 9 * s * wsp), ri(ccy - 5 * s)), max(1, ri(1.8 * s)))
    _oell(surf, body_c, out, ccx, ccy, 2.2 * s, 9 * s)
    for sgn in (-1, 1):
        pygame.draw.line(surf, body_c, (ri(ccx), ri(ccy - 8 * s)), (ri(ccx + sgn * 3 * s), ri(ccy - 12 * s)), max(1, ri(1 * s)))
        pygame.draw.circle(surf, body_c, (ri(ccx + sgn * 3 * s), ri(ccy - 12 * s)), max(1, ri(1.2 * s)))


# ===========================================================================
# dispatch + sprite metadata
# ===========================================================================
_DISPATCH = {
    "dog": _draw_dog, "rabbit": _draw_rabbit, "deer": _draw_deer, "sheep": _draw_sheep,
    "cow": _draw_cow, "frog": _draw_frog, "bird": _draw_bird,
    "fox": _draw_fox, "raccoon": _draw_raccoon, "squirrel": _draw_squirrel,
    "turtle": _draw_turtle, "pig": _draw_pig, "goat": _draw_goat, "chicken": _draw_chicken,
    "duck": _draw_duck, "horse": _draw_horse, "owl": _draw_owl,
    "hedgehog": _draw_hedgehog, "tanuki": _draw_tanuki, "butterfly": _draw_butterfly,
}

# span = (width, height) of the local draw surface in s-units, foot = how far the
# ground line sits from the bottom edge, shadow = contact shadow size in s-units
SPRITE = {
    "dog":      dict(span=(88, 84),  foot=8, shadow=(40, 11)),
    "rabbit":   dict(span=(66, 92),  foot=8, shadow=(28, 8)),
    "deer":     dict(span=(80, 104), foot=8, shadow=(36, 11)),
    "sheep":    dict(span=(82, 78),  foot=8, shadow=(42, 12)),
    "cow":      dict(span=(92, 80),  foot=8, shadow=(46, 13)),
    "frog":     dict(span=(58, 54),  foot=7, shadow=(30, 9)),
    "bird":     dict(span=(54, 60),  foot=6, shadow=(22, 7)),
    "fox":      dict(span=(86, 78),  foot=8, shadow=(40, 11)),
    "raccoon":  dict(span=(84, 78),  foot=8, shadow=(38, 11)),
    "squirrel": dict(span=(62, 82),  foot=8, shadow=(28, 9)),
    "turtle":   dict(span=(58, 50),  foot=6, shadow=(38, 10)),
    "pig":      dict(span=(88, 76),  foot=8, shadow=(44, 12)),
    "goat":     dict(span=(82, 82),  foot=8, shadow=(38, 11)),
    "chicken":  dict(span=(58, 82),  foot=8, shadow=(24, 8)),
    "duck":     dict(span=(64, 72),  foot=8, shadow=(30, 9)),
    "horse":    dict(span=(88, 98),  foot=8, shadow=(44, 12)),
    "owl":      dict(span=(58, 78),  foot=8, shadow=(26, 8)),
    "hedgehog": dict(span=(62, 50),  foot=7, shadow=(34, 10)),
    "tanuki":   dict(span=(86, 78),  foot=8, shadow=(40, 11)),
    "butterfly":dict(span=(48, 56),  foot=4, shadow=(14, 5)),
}
SPECIES_KEYS = list(SPRITE.keys())


def draw_animal(surf, x, y, key, facing, t, scale, state="idle", y_off=0.0,
                mood="neutral", phase=0.0, blink=False, draw_shadow=True,
                swim=0.0, fade=0.0, dance=0.0):
    """Paint one animal with its ground contact point at (x, y).

    Mirrors :func:`render.cat.draw_cat`: a per-sprite surface is painted facing
    right, flipped for ``facing == -1`` and blitted at the bottom-centre anchor.
    Pose flags (idle breathing, walk swing + head bob + ear twitch, hop, cozy
    lying sleep, play, and listening -- a settled body bobbing on the song's
    real beat) are derived here so the painters only describe the look.
    """
    s = scale
    if s <= 0:
        return
    spec = SPRITE.get(key)
    if spec is None:
        return

    sleeping = state == "sleep"
    airborne = y_off > 0.5 or state == "hop"
    playing = state == "play"
    listening = state == "listen"
    moving = state in ("walk", "hop")

    ph = (t + phase) * _WALK_F
    if airborne:
        step = 0.0
        bob = 0.0
    elif sleeping:
        step = 0.0
        bob = 1.2 * s + math.sin((t + phase) * 1.5) * 0.6 * s
    elif listening:
        # a happy little head-nod locked to the actual beat of Bal's song
        step = 0.0
        bob = -abs(math.sin(dance * math.pi)) * 2.2 * s
    elif moving:
        step = math.sin(ph)
        bob = -abs(math.sin(ph)) * 3.0 * s
    else:
        step = 0.0
        bob = math.sin((t + phase) * 2.0) * 1.0 * s

    # a small head counter-bob and ear twitch give every animal a pulse of life
    if airborne:
        headbob = -1.2 * s
    elif moving:
        headbob = math.sin(ph + 0.7) * 1.1 * s
    else:
        headbob = math.sin((t + phase) * 2.0 + 0.6) * 0.7 * s
    if listening:
        headbob = -abs(math.sin(dance * math.pi + 0.35)) * 1.4 * s
    ear = math.sin((t + phase) * 3.3) * 0.6 * s + (math.sin(ph) * 0.5 * s if moving else 0.0)
    lean = 1.6 * s if moving else 0.0

    a = dict(t=t + phase, step=step, bob=bob, headbob=headbob, ear=ear, lean=lean,
             airborne=airborne, sleeping=sleeping, rest=sleeping, moving=moving,
             mood=("happy" if (playing or listening) else mood), blink=blink,
             state=state)

    span = spec["span"]
    Wl = max(4, ri(span[0] * s) + 8)
    Hl = max(4, ri(span[1] * s) + 8)
    spr = pygame.Surface((Wl, Hl), pygame.SRCALPHA)
    cxl = Wl * 0.5
    gyl = Hl - spec["foot"] * s

    _DISPATCH[key](spr, cxl, gyl, s, a)

    if playing:
        _sparkle(spr, cxl + span[0] * 0.18 * s, gyl - span[1] * 0.74 * s, s)
        _sparkle(spr, cxl - span[0] * 0.06 * s, gyl - span[1] * 0.88 * s, s * 0.8)
    if listening and math.sin(dance * math.pi) > 0.55:
        # a tiny sparkle right on the beat, so the whole ring twinkles in time
        _sparkle(spr, cxl + span[0] * 0.16 * s, gyl - span[1] * 0.86 * s, s * 0.7)
    if sleeping:
        _zzz(spr, cxl + span[0] * 0.18 * s, gyl - span[1] * 0.55 * s, s, t + phase)

    # haze into the distance, like the props do
    if fade > 0.0:
        tint = pygame.Surface((Wl, Hl), pygame.SRCALPHA)
        tint.fill((212, 223, 205, int(clamp(fade, 0, 1) * 175)))
        spr.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    # semi-aquatic: clip below a softly waving waterline and sink, like the cat
    water_sink = 0.0
    if swim > 0.05:
        w = clamp((swim - 0.10) / 0.90, 0.0, 1.0)
        feet = gyl - 2 * s
        high = gyl - span[1] * 0.42 * s
        base_wl = lerp(feet, high, w)
        water_sink = gyl - base_wl
        amp = (0.7 + 0.8 * w) * s
        phs = t * 4.0 + x * 0.02
        for cxp in range(0, Wl):
            wl = base_wl + math.sin(cxp * 0.5 + phs) * amp
            wli = ri(clamp(wl, 0.0, float(Hl)))
            if wli < Hl:
                spr.fill((0, 0, 0, 0), (cxp, wli, 1, Hl - wli))

    # soft contact shadow on the ground (skipped while swimming / high hops)
    if draw_shadow and swim <= 0.05:
        lift_frac = clamp(y_off / (90.0 * s), 0.0, 1.0)
        shw, shh = spec["shadow"]
        sw_ = (shw - shw * 0.4 * lift_frac) * s
        shh_ = (shh - shh * 0.4 * lift_frac) * s
        al = int(115 * (1.0 - 0.5 * lift_frac))
        shs = pygame.Surface((max(2, ri(sw_) + 4), max(2, ri(shh_) + 4)), pygame.SRCALPHA)
        scx, scy = shs.get_width() / 2.0, shs.get_height() / 2.0
        pygame.draw.ellipse(shs, (40, 40, 52, al), (ri(scx - sw_ / 2), ri(scy - shh_ / 2), max(2, ri(sw_)), max(2, ri(shh_))))
        surf.blit(shs, (ri(x - shs.get_width() / 2), ri(y - shs.get_height() / 2)))

    if facing == -1:
        spr = pygame.transform.flip(spr, True, False)

    surf.blit(spr, (ri(x - cxl), ri((y - y_off + water_sink) - gyl)))
