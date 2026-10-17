"""Procedural icons for musical components.

One function, :func:`draw_icon`, paints a chunky softly-outlined glyph for each
component icon style (note, stone, cluster, orb, crystal, rune, cassette, star,
fruit, plus a generic fallback).  It is resolution independent -- give it a
centre, a radius and a colour -- so the same code draws the tiny floating pickup
in the world and the bigger icon on the discovery card and in the Music Maker
browser.
"""

import math

import pygame


def _outline(col, amt=70):
    return (max(0, col[0] - amt), max(0, col[1] - amt), max(0, col[2] - amt))


def _lighten(col, amt=40):
    return (min(255, col[0] + amt), min(255, col[1] + amt), min(255, col[2] + amt))


def draw_icon(surf, cx, cy, r, color, style="note", t=0.0):
    """Draw a component glyph centred at (cx, cy) with radius r."""
    cx, cy, r = int(cx), int(cy), max(3, int(r))
    ol = _outline(color)
    hi = _lighten(color)

    if style == "note":
        # round note head with a stem and flag
        head_r = max(2, int(r * 0.55))
        hx, hy = cx - int(r * 0.25), cy + int(r * 0.35)
        pygame.draw.line(surf, ol, (hx + head_r - 1, hy),
                         (hx + head_r - 1, cy - r), max(2, r // 5))
        pygame.draw.circle(surf, color, (hx, hy), head_r)
        pygame.draw.circle(surf, ol, (hx, hy), head_r, max(1, r // 6))
        pygame.draw.circle(surf, hi, (hx - head_r // 3, hy - head_r // 3),
                           max(1, head_r // 3))
        # flag
        fx, fy = hx + head_r - 1, cy - r
        pygame.draw.line(surf, color, (fx, fy), (fx + int(r * 0.6), fy + int(r * 0.4)),
                         max(2, r // 4))

    elif style == "stone":
        # rounded rhythm pebble with a pulse ring
        rect = pygame.Rect(0, 0, int(r * 1.7), int(r * 1.3))
        rect.center = (cx, cy)
        pygame.draw.ellipse(surf, color, rect)
        pygame.draw.ellipse(surf, ol, rect, max(1, r // 6))
        hr = rect.inflate(-rect.w // 2, -rect.h // 2)
        hr.center = (cx - r // 4, cy - r // 4)
        pygame.draw.ellipse(surf, hi, hr)

    elif style == "cluster":
        # three small orbs orbiting -> a chord
        for i in range(3):
            a = t * 1.5 + i * (2 * math.pi / 3)
            ox = cx + int(math.cos(a) * r * 0.5)
            oy = cy + int(math.sin(a) * r * 0.4)
            pygame.draw.circle(surf, color, (ox, oy), max(2, r // 2))
            pygame.draw.circle(surf, ol, (ox, oy), max(2, r // 2), max(1, r // 7))
            pygame.draw.circle(surf, hi, (ox - r // 6, oy - r // 6), max(1, r // 6))

    elif style == "orb":
        # soft glowing ambient orb
        glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        for i, a in enumerate((40, 80, 150)):
            rr = int(r * (1.6 - i * 0.4))
            pygame.draw.circle(glow, (*color, a), (r * 2, r * 2), rr)
        surf.blit(glow, (cx - r * 2, cy - r * 2))
        pygame.draw.circle(surf, hi, (cx - r // 4, cy - r // 4), max(1, r // 3))

    elif style == "crystal":
        # faceted gem (effect)
        pts = [(cx, cy - r), (cx + int(r * 0.7), cy - int(r * 0.2)),
               (cx + int(r * 0.4), cy + r), (cx - int(r * 0.4), cy + r),
               (cx - int(r * 0.7), cy - int(r * 0.2))]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, ol, pts, max(1, r // 6))
        pygame.draw.line(surf, hi, (cx, cy - r), (cx, cy + r), max(1, r // 7))
        pygame.draw.line(surf, hi, (cx, cy - r), (cx - int(r * 0.7), cy - int(r * 0.2)),
                         max(1, r // 8))

    elif style == "rune":
        # carved tablet with a glyph (rhythm/texture)
        rect = pygame.Rect(0, 0, int(r * 1.5), int(r * 1.9))
        rect.center = (cx, cy)
        pygame.draw.rect(surf, color, rect, border_radius=max(2, r // 4))
        pygame.draw.rect(surf, ol, rect, max(1, r // 6), border_radius=max(2, r // 4))
        gy = rect.y + rect.h // 4
        pygame.draw.line(surf, hi, (rect.x + rect.w // 4, gy),
                         (rect.right - rect.w // 4, gy), max(1, r // 7))
        pygame.draw.line(surf, hi, (cx, gy), (cx, rect.bottom - rect.h // 4),
                         max(1, r // 7))

    elif style == "cassette":
        # little tape (loop)
        rect = pygame.Rect(0, 0, int(r * 2.0), int(r * 1.3))
        rect.center = (cx, cy)
        pygame.draw.rect(surf, color, rect, border_radius=max(2, r // 5))
        pygame.draw.rect(surf, ol, rect, max(1, r // 6), border_radius=max(2, r // 5))
        for sx in (cx - r // 2, cx + r // 2):
            pygame.draw.circle(surf, hi, (sx, cy), max(2, r // 3))
            pygame.draw.circle(surf, ol, (sx, cy), max(2, r // 3), 1)

    elif style == "star":
        # five-point rare star
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.45
            pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, ol, pts, max(1, r // 7))
        pygame.draw.circle(surf, hi, (cx, cy), max(1, r // 4))

    elif style == "fruit":
        # cherry-like sound fruit
        pygame.draw.circle(surf, color, (cx, cy + r // 3), int(r * 0.8))
        pygame.draw.circle(surf, ol, (cx, cy + r // 3), int(r * 0.8), max(1, r // 6))
        pygame.draw.circle(surf, hi, (cx - r // 4, cy), max(1, r // 4))
        pygame.draw.line(surf, _outline((90, 150, 90), 0), (cx, cy - r // 3),
                         (cx + r // 3, cy - r), max(1, r // 7))

    elif style == "droplet":
        # water droplet (teardrop) with a soft highlight
        pts = [(cx, cy - r),
               (cx + int(r * 0.7), cy + int(r * 0.35)),
               (cx, cy + r),
               (cx - int(r * 0.7), cy + int(r * 0.35))]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.circle(surf, color, (cx, cy + int(r * 0.35)), int(r * 0.7))
        pygame.draw.circle(surf, ol, (cx, cy + int(r * 0.35)), int(r * 0.7), max(1, r // 6))
        pygame.draw.circle(surf, hi, (cx - r // 4, cy + r // 6), max(1, r // 4))

    elif style == "feather":
        # a soft feather: curved spine with little barbs
        tip = (cx + int(r * 0.55), cy - r)
        base = (cx - int(r * 0.55), cy + r)
        pygame.draw.line(surf, ol, base, tip, max(2, r // 4))
        for i in range(1, 6):
            f = i / 6.0
            mx = int(base[0] + (tip[0] - base[0]) * f)
            my = int(base[1] + (tip[1] - base[1]) * f)
            spread = int(r * 0.5 * (1 - f) + r * 0.12)
            pygame.draw.line(surf, color, (mx, my), (mx - spread, my - spread // 2), max(1, r // 7))
            pygame.draw.line(surf, color, (mx, my), (mx + spread // 2, my - spread // 2), max(1, r // 7))
        pygame.draw.circle(surf, hi, tip, max(1, r // 6))

    elif style == "moon":
        # crescent moon (owl / night flavour)
        pygame.draw.circle(surf, color, (cx, cy), r)
        pygame.draw.circle(surf, ol, (cx, cy), r, max(1, r // 7))
        # carve the crescent with the background-ish dark offset circle
        pygame.draw.circle(surf, _outline(color, 30), (cx + int(r * 0.5), cy - int(r * 0.2)),
                           int(r * 0.9))
        pygame.draw.circle(surf, hi, (cx - int(r * 0.35), cy + int(r * 0.1)), max(1, r // 4))

    elif style == "paw":
        # paw print: main pad + four toe beans
        pygame.draw.ellipse(surf, color, pygame.Rect(cx - int(r * 0.55), cy - int(r * 0.1),
                                                     int(r * 1.1), int(r * 0.95)))
        pygame.draw.ellipse(surf, ol, pygame.Rect(cx - int(r * 0.55), cy - int(r * 0.1),
                                                  int(r * 1.1), int(r * 0.95)), max(1, r // 7))
        toes = [(-0.5, -0.7), (-0.15, -0.95), (0.2, -0.95), (0.55, -0.65)]
        for dx, dy in toes:
            tx, ty = cx + int(dx * r), cy + int(dy * r)
            pygame.draw.circle(surf, color, (tx, ty), max(2, int(r * 0.26)))
            pygame.draw.circle(surf, ol, (tx, ty), max(2, int(r * 0.26)), 1)

    elif style == "ring":
        # concentric echo rings (delay / reverb effects)
        for i, rr in enumerate((r, int(r * 0.66), int(r * 0.34))):
            col = color if i % 2 == 0 else hi
            pygame.draw.circle(surf, col, (cx, cy), max(1, rr), max(1, r // 6))
        pygame.draw.circle(surf, hi, (cx, cy), max(1, r // 6))

    elif style == "wisp":
        # a curling wind swirl
        for k in range(3):
            base_a = t * 0.8 + k * 2.1
            pts = []
            for j in range(10):
                a = base_a + j * 0.5
                rad = r * (0.25 + 0.07 * j)
                pts.append((cx + int(math.cos(a) * rad),
                            cy + int(math.sin(a) * rad * 0.7)))
            if len(pts) > 1:
                pygame.draw.lines(surf, color if k < 2 else hi, False, pts, max(1, r // 7))

    else:                                    # generic dot
        pygame.draw.circle(surf, color, (cx, cy), r)
        pygame.draw.circle(surf, ol, (cx, cy), r, max(1, r // 6))
        pygame.draw.circle(surf, hi, (cx - r // 4, cy - r // 4), max(1, r // 4))
