"""The cat sprite painter - body, head, ears, tail, legs, the paw-swat pose and
the wet/submerged look while swimming.

Pure drawing: it takes plain values, not a :class:`~cat_society.entities.cat.Cat`,
so entity state and rendering stay decoupled."""

import math

import pygame

from ..config import ATTACK_DUR
from ..utils import ri, clamp, lerp, lerp_color
from ..palette import FW_SHALLOW


def draw_cat(surf, x, y, facing, t, scale=1.0, moving=False, running=False,
             blink=False, y_off=0.0, attack_t=0.0, expression="neutral",
             sleeping=False, draw_shadow=True, swim=0.0,
             airborne_override=None, palette=None):
    """Cozy pixel chibi cat. Big round head, little body on stubby legs, soft
    ears, a wee scarf, a waggy tail, dot eyes, and a few moods. Drawn facing
    right, then flipped. (x, y) is the ground contact point."""
    s = scale
    if s <= 0:
        return

    palette = palette or {}
    fur = tuple(palette.get("fur", (250, 201, 160)))
    fur_d = tuple(palette.get("fur_d", (226, 170, 132)))
    fur_l = tuple(palette.get("fur_l", (255, 226, 192)))
    out = tuple(palette.get("out", (150, 108, 84)))
    ear_in = tuple(palette.get("ear_in", (255, 176, 196)))
    eye = tuple(palette.get("eye", (54, 58, 70)))
    white = tuple(palette.get("white", (255, 255, 255)))
    nose_c = tuple(palette.get("nose", (240, 128, 140)))
    scarf = tuple(palette.get("scarf", (240, 108, 108)))
    scarf_d = tuple(palette.get("scarf_d", (206, 78, 86)))
    blush = tuple(palette.get("blush", (255, 174, 184)))
    tear_c = tuple(palette.get("tear", (150, 205, 245)))

    airborne = (y_off > 0.5 if airborne_override is None
                else bool(airborne_override))
    attacking = attack_t > 0.0
    sleeping = sleeping and not airborne
    if sleeping:
        moving = False
        running = False
    ap = (1.0 - attack_t / ATTACK_DUR) if attacking else 0.0
    ext = math.sin(ap * math.pi) if attacking else 0.0

    walk_f = 13.0 if running else 9.0
    ph = t * walk_f
    step = math.sin(ph)
    if airborne:
        bob = 0.0
    elif sleeping:
        bob = 12.0 * s + math.sin(t * 1.6) * 0.8 * s
    elif moving:
        bob = -abs(math.sin(ph)) * (3.0 if running else 2.0) * s
    else:
        bob = math.sin(t * 2.2) * 1.0 * s
    lean = (3.0 * s if running else 0.0) + ext * 5.0 * s

    SW = max(1, ri(160 * s))
    SH = max(1, ri(110 * s))
    cat = pygame.Surface((SW, SH), pygame.SRCALPHA)
    fx = 66.0 * s
    fy = SH - 12.0 * s

    bw, bh = 50.0 * s, 30.0 * s
    body_cx = fx + lean * 0.5
    body_cy = fy - 27.0 * s + bob
    body_bottom = body_cy + bh * 0.5

    head_r = 21.0 * s
    head_cx = fx + 9.0 * s + lean
    head_cy = body_cy - 19.0 * s

    ground_foot = fy - 1.0 * s
    stride = 4.0 * s
    lift = 3.0 * s

    def foot(bx, sign):
        if airborne:
            return (bx, body_bottom + 5.0 * s)
        if moving and not attacking:
            sg = step * sign
            return (bx + sg * stride, ground_foot - max(0.0, sg) * lift)
        return (bx, ground_foot)

    nb_x = body_cx - bw * 0.24
    nf_x = body_cx + bw * 0.20
    fb_x = body_cx - bw * 0.12
    ff_x = body_cx + bw * 0.10
    nb = foot(nb_x, -1.0)
    nf = foot(nf_x, +1.0)
    fb = foot(fb_x, +1.0)
    ff = foot(ff_x, -1.0)

    legw = max(2, ri(5 * s))
    legw_f = max(2, ri(4 * s))

    def leg(hipx, ft, far):
        c = fur_d if far else fur
        w = legw_f if far else legw
        pygame.draw.line(cat, c, (ri(hipx), ri(body_bottom - 2 * s)), (ri(ft[0]), ri(ft[1])), w)
        pw = max(2, ri((6 if not far else 5) * s))
        phh = max(1, ri(3 * s))
        pygame.draw.ellipse(cat, c, (ri(ft[0] - pw * 0.4), ri(ft[1] - phh * 0.5), pw, phh))

    # tail flowing out behind the body with a gentle lift and a wagging tip
    tbx = body_cx - bw * 0.42
    tby = body_cy - bh * 0.02
    tspeed = 6.0 if running else (4.0 if moving else 2.2)
    sway = math.sin(t * tspeed) * 5.0 * s
    seg = [(tbx, tby),
           (tbx - 12 * s, tby - 4 * s),
           (tbx - 21 * s, tby - 8 * s + sway * 0.5),
           (tbx - 28 * s, tby - 11 * s + sway * 1.0)]
    rad = [5.0, 4.2, 3.4, 2.8]
    dense = []
    for i in range(len(seg) - 1):
        for f in (0.0, 0.5):
            dense.append((lerp(seg[i][0], seg[i + 1][0], f),
                          lerp(seg[i][1], seg[i + 1][1], f),
                          lerp(rad[i], rad[i + 1], f)))
    dense.append((seg[-1][0], seg[-1][1], rad[-1]))
    for px, py, r in dense:
        pygame.draw.circle(cat, out, (ri(px), ri(py)), max(1, ri(r * s) + 1))
    for px, py, r in dense:
        pygame.draw.circle(cat, fur, (ri(px), ri(py)), max(1, ri(r * s)))
    pygame.draw.circle(cat, fur_l, (ri(seg[-1][0]), ri(seg[-1][1])), max(1, ri(2.0 * s)))

    # far legs
    leg(fb_x, fb, True)
    leg(ff_x, ff, True)

    # body
    bx0, by0 = ri(body_cx - bw / 2), ri(body_cy - bh / 2)
    pygame.draw.ellipse(cat, out, (bx0 - 1, by0 - 1, ri(bw) + 2, ri(bh) + 2))
    pygame.draw.ellipse(cat, fur, (bx0, by0, ri(bw), ri(bh)))
    pygame.draw.ellipse(cat, fur_l, (ri(body_cx - bw * 0.28), ri(body_cy - bh * 0.02),
                                     max(1, ri(bw * 0.46)), max(1, ri(bh * 0.44))))

    # near legs
    leg(nb_x, nb, False)
    if not attacking:
        leg(nf_x, nf, False)

    # ears (drawn before head fill so the head tucks over their base)
    def ear(pts3):
        p = [(ri(a), ri(b)) for a, b in pts3]
        pygame.draw.polygon(cat, out, p)
        cxx = sum(q[0] for q in p) / 3.0
        cyy = sum(q[1] for q in p) / 3.0
        inner = [(ri(lerp(q[0], cxx, 0.34)), ri(lerp(q[1], cyy, 0.34))) for q in p]
        pygame.draw.polygon(cat, fur, inner)
        pink = [(ri(lerp(q[0], cxx, 0.62)), ri(lerp(q[1], cyy, 0.62))) for q in p]
        pygame.draw.polygon(cat, ear_in, pink)

    ear([(head_cx - head_r * 0.78, head_cy - head_r * 0.32),
         (head_cx - head_r * 0.14, head_cy - head_r * 0.60),
         (head_cx - head_r * 0.58, head_cy - head_r - 7 * s)])
    ear([(head_cx + head_r * 0.14, head_cy - head_r * 0.60),
         (head_cx + head_r * 0.78, head_cy - head_r * 0.32),
         (head_cx + head_r * 0.58, head_cy - head_r - 7 * s)])

    # head
    hr = max(2, ri(head_r))
    pygame.draw.circle(cat, out, (ri(head_cx), ri(head_cy)), hr + 1)
    pygame.draw.circle(cat, fur, (ri(head_cx), ri(head_cy)), hr)
    pygame.draw.circle(cat, fur_l, (ri(head_cx - head_r * 0.34), ri(head_cy - head_r * 0.26)),
                       max(1, ri(head_r * 0.34)))

    # face
    ex = 7.0 * s
    eyl = (head_cx - ex, head_cy - 0.5 * s)
    eyr = (head_cx + ex, head_cy - 0.5 * s)
    es = max(2, ri(3.0 * s))
    nose_y = head_cy + 5.5 * s

    def dot_eye(c, dy=0.0):
        rx, ry = ri(c[0] - es / 2), ri(c[1] - es / 2 + dy)
        pygame.draw.rect(cat, eye, (rx, ry, es, es))
        cat.set_at((rx, ry), white)

    def closed_eye(c):
        pygame.draw.line(cat, eye, (ri(c[0] - 3 * s), ri(c[1])), (ri(c[0] + 3 * s), ri(c[1])), max(1, ri(1.5 * s)))

    def happy_eye(c):
        a = (ri(c[0] - 3 * s), ri(c[1] + 1 * s))
        b = (ri(c[0]), ri(c[1] - 2 * s))
        d = (ri(c[0] + 3 * s), ri(c[1] + 1 * s))
        pygame.draw.lines(cat, eye, False, [a, b, d], max(1, ri(1.5 * s)))

    def nose():
        pygame.draw.circle(cat, nose_c, (ri(head_cx), ri(nose_y)), max(1, ri(1.8 * s)))

    def mouth_y():
        pygame.draw.line(cat, eye, (ri(head_cx), ri(nose_y)), (ri(head_cx), ri(nose_y + 3 * s)), max(1, ri(1 * s)))
        pygame.draw.line(cat, eye, (ri(head_cx), ri(nose_y + 3 * s)), (ri(head_cx - 3 * s), ri(nose_y + 5 * s)), max(1, ri(1 * s)))
        pygame.draw.line(cat, eye, (ri(head_cx), ri(nose_y + 3 * s)), (ri(head_cx + 3 * s), ri(nose_y + 5 * s)), max(1, ri(1 * s)))

    def smile():
        pygame.draw.arc(cat, eye, (ri(head_cx - 4 * s), ri(nose_y + 1 * s), ri(8 * s), ri(7 * s)),
                        1.15 * math.pi, 1.85 * math.pi, max(1, ri(1.4 * s)))

    def frown():
        pygame.draw.arc(cat, eye, (ri(head_cx - 4 * s), ri(nose_y + 4 * s), ri(8 * s), ri(6 * s)),
                        0.15 * math.pi, 0.85 * math.pi, max(1, ri(1.4 * s)))

    def blush_at(cx):
        pygame.draw.rect(cat, blush, (ri(cx - 2 * s), ri(head_cy + 2.5 * s), max(2, ri(4 * s)), max(1, ri(2 * s))))

    if sleeping:
        closed_eye(eyl)
        closed_eye(eyr)
        nose()
        mouth_y()
        blush_at(head_cx - head_r * 0.62)
        blush_at(head_cx + head_r * 0.62)
        # floating z z
        for i in range(2):
            zz = (t * 1.4 + i * 0.5) % 2.0
            zx = ri(head_cx + head_r * 0.5 + i * 4 * s + zz * 2 * s)
            zy = ri(head_cy - head_r - 2 * s - zz * 5 * s)
            zs = max(2, ri(3 * s))
            pygame.draw.line(cat, white, (zx, zy), (zx + zs, zy), max(1, ri(1 * s)))
            pygame.draw.line(cat, white, (zx + zs, zy), (zx, zy + zs), max(1, ri(1 * s)))
            pygame.draw.line(cat, white, (zx, zy + zs), (zx + zs, zy + zs), max(1, ri(1 * s)))
    elif expression == "happy":
        if blink:
            closed_eye(eyl)
            closed_eye(eyr)
        else:
            happy_eye(eyl)
            happy_eye(eyr)
        blush_at(head_cx - head_r * 0.62)
        blush_at(head_cx + head_r * 0.62)
        nose()
        smile()
    elif expression == "sad":
        dot_eye(eyl, dy=1.2 * s)
        dot_eye(eyr, dy=1.2 * s)
        pygame.draw.line(cat, out, (ri(eyl[0] - 3 * s), ri(eyl[1] - 5 * s)), (ri(eyl[0] + 2 * s), ri(eyl[1] - 6 * s)), max(1, ri(1 * s)))
        pygame.draw.line(cat, out, (ri(eyr[0] - 2 * s), ri(eyr[1] - 6 * s)), (ri(eyr[0] + 3 * s), ri(eyr[1] - 5 * s)), max(1, ri(1 * s)))
        nose()
        frown()
        cat.set_at((ri(eyl[0]), ri(eyl[1] + 4 * s)), tear_c)
        cat.set_at((ri(eyl[0]), ri(eyl[1] + 5 * s)), tear_c)
    elif expression == "angry":
        dot_eye(eyl)
        dot_eye(eyr)
        pygame.draw.line(cat, out, (ri(eyl[0] - 3 * s), ri(eyl[1] - 6 * s)), (ri(eyl[0] + 3 * s), ri(eyl[1] - 3 * s)), max(1, ri(1.4 * s)))
        pygame.draw.line(cat, out, (ri(eyr[0] + 3 * s), ri(eyr[1] - 6 * s)), (ri(eyr[0] - 3 * s), ri(eyr[1] - 3 * s)), max(1, ri(1.4 * s)))
        nose()
        frown()
    else:  # neutral
        if blink:
            closed_eye(eyl)
            closed_eye(eyr)
        else:
            dot_eye(eyl)
            dot_eye(eyr)
        nose()
        mouth_y()
        blush_at(head_cx - head_r * 0.62)
        blush_at(head_cx + head_r * 0.62)

    # scarf: soft band around the neck with two little tails
    neck_y = head_cy + head_r + 0.5 * s
    band = (ri(head_cx - 15 * s), ri(neck_y - 3 * s), max(2, ri(30 * s)), max(2, ri(7 * s)))
    pygame.draw.rect(cat, scarf, band)
    pygame.draw.rect(cat, scarf_d, (band[0], band[1] + band[3] - max(1, ri(2 * s)), band[2], max(1, ri(2 * s))))
    knot = (head_cx + 9.0 * s, neck_y + 1.0 * s)
    pygame.draw.line(cat, scarf, (ri(knot[0] - 1 * s), ri(knot[1] + 2 * s)), (ri(knot[0] - 4 * s), ri(knot[1] + 10 * s)), max(2, ri(3 * s)))
    pygame.draw.line(cat, scarf, (ri(knot[0] + 2 * s), ri(knot[1] + 2 * s)), (ri(knot[0] + 6 * s), ri(knot[1] + 9 * s)), max(2, ri(3 * s)))
    pygame.draw.circle(cat, scarf, (ri(knot[0]), ri(knot[1])), max(2, ri(3 * s)))
    pygame.draw.circle(cat, scarf_d, (ri(knot[0]), ri(knot[1])), max(2, ri(3 * s)), max(1, ri(1 * s)))

    # attack paw
    if attacking:
        shoulder = (body_cx + bw * 0.30, body_cy + 1.0 * s)
        arm_len = 15.0 * s
        a_rest = math.radians(36)
        a_up = math.radians(-8)
        ang = a_rest + (a_up - a_rest) * ext
        wrist = (shoulder[0] + math.cos(ang) * arm_len, shoulder[1] + math.sin(ang) * arm_len)
        pygame.draw.line(cat, fur, (ri(shoulder[0]), ri(shoulder[1])), (ri(wrist[0]), ri(wrist[1])), max(2, ri(6 * s)))
        pw = max(2, ri(6 * s))
        phh = max(1, ri(3 * s))
        pygame.draw.ellipse(cat, fur, (ri(wrist[0] - pw * 0.4), ri(wrist[1] - phh * 0.5), pw, phh))
        if ext > 0.5:
            for k in range(3):
                sx_ = ri(wrist[0] + (3 + k * 2) * s)
                sy_ = ri(wrist[1] - (4 + k) * s)
                cat.set_at((clamp(sx_, 0, SW - 1), clamp(sy_, 0, SH - 1)), (255, 255, 255))

    # --- swimming / wading: the cat sits IN the water, submerged by an amount
    #     that tracks the real depth.  The waterline is a gentle wave, not a
    #     ruler-straight cut, and the cat bobs and sways as if paddling. ---
    swim_bob = 0.0
    swim_sway = 0.0
    water_sink = 0.0
    if swim > 0.05:
        w = clamp((swim - 0.10) / 0.90, 0.0, 1.0)     # 0 = ankle deep, 1 = swimming
        feet_line = body_bottom + 4.0 * s
        high_line = body_cy - bh * 0.10               # only head/shoulders left
        base_wl = lerp(feet_line, high_line, w)
        # KEY GROUNDING FIX: the contact point (fy) is the water SURFACE, so the
        # waterline on the body must be drawn there too.  We sink the whole
        # sprite by the gap between its feet and the waterline, which makes the
        # cat sit IN the water at the surface instead of hovering above it.
        water_sink = fy - base_wl
        amp = (0.8 + 1.0 * w) * s
        phase = t * 4.0 + x * 0.02
        hx0 = max(0, ri(body_cx - bw * 0.62))
        hx1 = min(SW - 1, ri(body_cx + bw * 0.62))
        shim = lerp_color(FW_SHALLOW, (255, 255, 255), 0.30)
        # clear everything below a softly waving waterline, column by column
        for cxp in range(0, SW):
            wl = base_wl + math.sin(cxp * 0.5 + phase) * amp
            wli = ri(clamp(wl, 0.0, float(SH)))
            if wli < SH:
                cat.fill((0, 0, 0, 0), (cxp, wli, 1, SH - wli))
            # a little shimmer right at the waterline across the body
            if hx0 <= cxp <= hx1 and 0 <= wli < SH:
                cat.set_at((cxp, wli), shim)
        swim_bob = math.sin(t * 2.8 + x * 0.01) * (1.0 + 1.2 * w) * s
        swim_sway = math.sin(t * 3.4 + x * 0.013) * 1.1 * w * s

    # ground shadow + blit  (no cast shadow while swimming: it's underwater)
    if draw_shadow and swim <= 0.05:
        lift_frac = clamp(y_off / (120.0 * s), 0.0, 1.0)
        sw_ = (60.0 - 22.0 * lift_frac) * s
        shh_ = (15.0 - 5.0 * lift_frac) * s
        a = int(120 * (1.0 - 0.45 * lift_frac))
        shs = pygame.Surface((max(2, ri(sw_) + 4), max(2, ri(shh_) + 4)), pygame.SRCALPHA)
        scx, scy = shs.get_width() / 2.0, shs.get_height() / 2.0
        pygame.draw.ellipse(shs, (40, 40, 52, a), (ri(scx - sw_ / 2), ri(scy - shh_ / 2), max(2, ri(sw_)), max(2, ri(shh_))))
        surf.blit(shs, (ri(x - shs.get_width() / 2), ri(y - shs.get_height() / 2)))

    if facing == -1:
        cat = pygame.transform.flip(cat, True, False)
        fx_eff = SW - fx
    else:
        fx_eff = fx
    surf.blit(cat, (ri(x - fx_eff + swim_sway), ri((y - y_off - swim_bob + water_sink) - fy)))
