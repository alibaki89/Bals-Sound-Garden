"""Painters for meadow props: trees, bushes, stones, flowers, tufts, mushrooms,
pebbles and the little buildings.

``_haze`` is the shared far-distance fade helper used by several other render
modules too."""

import math

import pygame

from .. import config
from ..config import *
from ..utils import ri, clamp, lerp_color, ground_color_at
from ..palette import *


TREES = [
    ((120, 192, 116), (158, 216, 150), (92, 162, 96), None, "blob"),       # spring
    ((246, 176, 206), (255, 208, 228), (224, 146, 184), (255, 240, 246), "blob"),  # sakura
    ((236, 150, 84), (250, 186, 112), (206, 116, 60), (250, 214, 120), "blob"),    # autumn
    ((240, 200, 96), (250, 224, 134), (210, 168, 70), None, "blob"),       # golden
    ((240, 158, 148), (250, 192, 182), (212, 128, 122), (255, 232, 224), "blob"),  # coral
    ((92, 156, 108), (120, 182, 132), (66, 124, 86), None, "pine"),        # pine
]


def _haze(fade):
    if fade > 0.0:
        return lambda c: lerp_color(c, HAZE, fade)
    return lambda c: c


def draw_prop(surf, kind, sx, sy, scale, seed, fade):
    # One object, one identity, at every distance. The shape, type and colour
    # come only from the seed. Distance changes the SIZE and the amount of fine
    # texture, never the silhouette. Every base sits on the projected ground sy.
    sx, sy = ri(sx), ri(sy)
    s = scale * config.SC * PROP_GROW.get(kind, 1.0)
    if s <= 0:
        return
    col = _haze(fade)
    mid = scale > 0.32        # medium detail (soft highlights)
    near = scale > 0.52       # fine detail (texture flecks, accents)

    # contact shadow only under the larger props; grass and small bits skip it
    if scale >= 0.14 and kind in ("tree", "bush", "stone", "mushroom"):
        sw, sht = {"tree": (52, 16), "bush": (44, 13), "stone": (32, 11),
                   "mushroom": (13, 5)}[kind]
        rw = ri(sw * s)
        rh = ri(sht * s)
        if rw >= 1 and rh >= 1:
            shc = lerp_color(ground_color_at(sy), GROUND_DEEP, 0.40 * (1.0 - fade))
            pygame.draw.ellipse(surf, shc, (sx - rw // 2, sy - rh // 2, rw, rh))

    if kind == "tuft":
        # A small fan of grass blades of varied height that lean gently outward,
        # so a clump reads as a real tussock of grass instead of a row of
        # identical vertical ticks.  Every blade's height/lean comes from the
        # seed, so each clump has its own character but is perfectly stable
        # frame-to-frame (no shimmer).
        hh = ri(10 * s)
        base = col((104, 178, 104))
        base_d = col((82, 154, 92))
        lit = col((158, 212, 142))
        if hh < 3:
            # too small for blades: a tidy soft dab rather than a lone pixel line
            cw = max(2, ri(3 * s))
            pygame.draw.line(surf, base, (sx, sy), (sx, sy - max(2, hh)), cw)
            if near:
                surf.set_at((clamp(sx, 0, config.W - 1), clamp(max(0, sy - hh), 0, config.H - 1)), lit)
            return
        bw = max(1, ri(2 * s))
        nb = 4 + (int(seed * 7) % 2)             # 4 or 5 blades
        for i in range(nb):
            f = (i + 0.5) / nb                   # 0..1 across the fan
            off = f - 0.5                        # -0.5..0.5 (centre = 0)
            spread = ri(off * 7.2 * s)           # base x within the clump
            lean = ri(off * 5.0 * s)             # tips fan outward like real grass
            # tall in the middle, shorter at the edges, plus a seeded per-blade
            # wobble so the silhouette never looks ruler-straight
            hfrac = 1.0 - abs(off) * 0.62 + 0.16 * math.sin(seed * 31.0 + i * 1.7)
            bh = max(2, ri(hh * clamp(hfrac, 0.45, 1.05)))
            bx = sx + spread
            tipx = bx + lean
            tipy = sy - bh
            pygame.draw.line(surf, base_d, (bx + 1, sy), (tipx + 1, tipy), bw)
            pygame.draw.line(surf, base, (bx, sy), (tipx, tipy), bw)
            if near and bh >= hh * 0.78:
                surf.set_at((clamp(tipx, 0, config.W - 1), clamp(tipy, 0, config.H - 1)), lit)
        return

    if kind == "flower":
        sh = ri(12 * s)
        petal = [(255, 152, 178), (255, 210, 128), (190, 174, 255),
                 (255, 246, 250), (255, 176, 150)][int(seed * 5) % 5]
        cy = sy - ri(13 * s)
        pr = ri(2.2 * s)
        stem = col((104, 168, 100))
        if pr < 1:
            if sh >= 1:
                pygame.draw.line(surf, stem, (sx, sy), (sx, sy - sh), 1)
            # a small designed bloom: a 2-wide petal dab with a warm centre,
            # not a single confetti pixel
            pc = col(petal)
            ctr = col(lerp_color(petal, (255, 240, 150), 0.45))
            bx = clamp(sx, 0, config.W - 1)
            by = clamp(max(0, cy), 0, config.H - 1)
            surf.set_at((bx, by), ctr)
            if bx + 1 < config.W:
                surf.set_at((bx + 1, by), pc)
            if bx - 1 >= 0:
                surf.set_at((bx - 1, by), pc)
            if by - 1 >= 0:
                surf.set_at((bx, by - 1), pc)
            return
        if sh >= 1:
            pygame.draw.line(surf, stem, (sx, sy), (sx, sy - sh), max(1, ri(2 * s)))
        pc = col(petal)
        pc_d = col(lerp_color(petal, (120, 90, 120), 0.20))
        for dx, dy in ((-pr, 0), (pr, 0), (0, -pr), (0, pr)):
            pygame.draw.circle(surf, pc, (sx + dx, cy + dy), pr)
        if near:
            # a hint of shade on the lower petals rounds the bloom
            pygame.draw.circle(surf, pc_d, (sx, cy + pr), max(1, ri(1.4 * s)))
        pygame.draw.circle(surf, col((255, 240, 140)), (sx, cy), max(1, ri(1.4 * s)))
        return

    if kind == "mushroom":
        sth = ri(7 * s)
        capr = ri(5 * s)
        if capr < 1:
            surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy - 1, 0, config.H - 1)), col((222, 92, 92)))
            return
        stw = max(1, ri(3 * s))
        if sth >= 1:
            pygame.draw.rect(surf, col((245, 238, 224)), (sx - stw // 2, sy - sth, stw, sth))
        cap = [(222, 92, 92), (210, 130, 86), (236, 160, 96)][int(seed * 3) % 3]
        pygame.draw.ellipse(surf, col(cap), (sx - capr, sy - sth - ri(3 * s), capr * 2, max(2, ri(6 * s))))
        # a soft lit crown so the cap reads as domed
        pygame.draw.ellipse(surf, col(lerp_color(cap, (255, 255, 255), 0.28)),
                            (sx - capr + max(1, ri(1 * s)), sy - sth - ri(3 * s),
                             max(2, ri(capr * 1.2)), max(1, ri(2.4 * s))))
        if near:
            surf.set_at((clamp(sx - ri(2 * s), 0, config.W - 1), clamp(sy - sth - ri(2 * s), 0, config.H - 1)), col((255, 252, 246)))
            surf.set_at((clamp(sx + ri(2 * s), 0, config.W - 1), clamp(sy - sth - ri(1 * s), 0, config.H - 1)), col((255, 248, 240)))
        return

    if kind == "pebble":
        r0 = ri(3 * s)
        if r0 < 1:
            surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy - 1, 0, config.H - 1)), col((176, 176, 186)))
            return
        pygame.draw.circle(surf, col((150, 150, 162)), (sx, sy - r0), r0)
        pygame.draw.circle(surf, col((178, 178, 190)), (sx, sy - r0), max(1, r0 - 1))
        if mid:
            r1 = max(1, ri(2 * s))
            pygame.draw.circle(surf, col((206, 206, 214)), (sx - max(1, ri(1 * s)), sy - r0 - max(0, ri(0.5 * s))), r1)
        return

    if kind == "bush":
        bw_ = ri(50 * s)
        if bw_ < 1:
            surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy - 1, 0, config.H - 1)), col((96, 176, 110)))
            return
        # rounded layered foliage: dark base, mid body, two lit crowns
        pygame.draw.ellipse(surf, col((68, 140, 90)), (sx - ri(25 * s), sy - ri(26 * s), max(1, ri(50 * s)), max(1, ri(30 * s))))
        pygame.draw.ellipse(surf, col((88, 168, 104)), (sx - ri(23 * s), sy - ri(28 * s), max(1, ri(46 * s)), max(1, ri(27 * s))))
        if mid:
            pygame.draw.ellipse(surf, col((116, 190, 126)), (sx - ri(16 * s), sy - ri(31 * s), max(1, ri(26 * s)), max(1, ri(16 * s))))
            pygame.draw.ellipse(surf, col((140, 206, 144)), (sx - ri(12 * s), sy - ri(31 * s), max(1, ri(16 * s)), max(1, ri(10 * s))))
            if near and seed < 0.5:
                for bx, by in ((-9, -16), (7, -13), (1, -8)):
                    pygame.draw.circle(surf, col((236, 104, 124)), (sx + ri(bx * s), sy + ri(by * s)), max(1, ri(2 * s)))
                    surf.set_at((clamp(sx + ri(bx * s), 0, config.W - 1), clamp(sy + ri(by * s) - 1, 0, config.H - 1)), col((255, 196, 206)))
        return

    if kind == "stone":
        sw_ = ri(34 * s)
        if sw_ < 1:
            surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy - 1, 0, config.H - 1)), col((150, 150, 162)))
            return
        # three-tone rounded boulder: shadow base, body, lit crown + rim
        pygame.draw.ellipse(surf, col((104, 104, 120)), (sx - ri(17 * s), sy - ri(18 * s), max(1, ri(34 * s)), max(1, ri(22 * s))))
        pygame.draw.ellipse(surf, col((142, 142, 156)), (sx - ri(15 * s), sy - ri(18 * s), max(1, ri(30 * s)), max(1, ri(18 * s))))
        if mid:
            pygame.draw.ellipse(surf, col((176, 176, 186)), (sx - ri(11 * s), sy - ri(18 * s), max(1, ri(16 * s)), max(1, ri(10 * s))))
            pygame.draw.ellipse(surf, col((206, 206, 214)), (sx - ri(9 * s), sy - ri(17 * s), max(1, ri(9 * s)), max(1, ri(5 * s))))
        return

    if kind == "tree":
        idx = int(seed * len(TREES)) % len(TREES)
        main_c, light_c, shade_c, accent_c, shape = TREES[idx]
        main_c, light_c, shade_c = col(main_c), col(light_c), col(shade_c)
        accent_c = col(accent_c) if accent_c else None
        trunk = col((124, 88, 60))
        trunk_d = col((98, 68, 46))
        trunk_l = col((150, 112, 78))

        if shape == "pine":
            if ri(28 * s) < 1:
                surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy - 1, 0, config.H - 1)), main_c)
                return
            th = ri(34 * s)
            tw = max(1, ri(7 * s))
            if th >= 1:
                pygame.draw.rect(surf, trunk, (sx - tw // 2, sy - th, tw, th))
                if near:
                    pygame.draw.rect(surf, trunk_d, (sx - tw // 2, sy - th, max(1, tw // 3), th))
                    pygame.draw.rect(surf, trunk_l, (sx + tw // 2 - max(1, tw // 4), sy - th, max(1, tw // 4), th))
            topy = sy - th + ri(3 * s)
            for half, dy in ((28, 0), (22, -14), (15, -26)):
                hw = ri(half * s)
                if hw < 1:
                    continue
                yb = topy + ri(dy * s)
                yt = yb - ri(16 * s)
                inset = max(1, ri(2 * s))
                pygame.draw.polygon(surf, shade_c, [(sx - hw, yb), (sx + hw, yb), (sx, yt)])
                pygame.draw.polygon(surf, main_c, [(sx - hw + inset, yb - 1),
                                                   (sx + hw - inset, yb - 1),
                                                   (sx, yt + inset)])
                if near:
                    pygame.draw.line(surf, light_c, (sx - hw + ri(3 * s), yb - ri(2 * s)),
                                     (sx, yt + ri(3 * s)), max(1, ri(1 * s)))
            if near:
                # tiny lit star on the top tier
                surf.set_at((clamp(sx, 0, config.W - 1), clamp(topy - ri(26 * s) - ri(15 * s), 0, config.H - 1)), light_c)
        else:
            if ri(23 * s) < 1:
                surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy - 1, 0, config.H - 1)), main_c)
                return
            th = ri(38 * s)
            tw = max(1, ri(8 * s))
            cy = sy - th - ri(6 * s)
            if th >= 1:
                pygame.draw.rect(surf, trunk, (sx - tw // 2, sy - th, tw, th))
                if near:
                    pygame.draw.rect(surf, trunk_d, (sx - tw // 2, sy - th, max(1, tw // 3), th))
                    pygame.draw.rect(surf, trunk_l, (sx + tw // 2 - max(1, tw // 4), sy - th, max(1, tw // 4), th))
            blobs = ((-13, 5, 19), (13, 5, 19), (0, -7, 23), (0, 7, 16))
            # dark outline pass (1px larger) for a clean readable silhouette
            for dx, dy, r in blobs:
                rr = ri((r + 1) * s)
                if rr >= 1:
                    pygame.draw.circle(surf, shade_c, (sx + ri(dx * s), cy + ri(dy * s)), rr)
            for dx, dy, r in blobs:
                rr = ri(r * s)
                if rr >= 1:
                    pygame.draw.circle(surf, main_c, (sx + ri(dx * s), cy + ri(dy * s)), rr)
            if mid:
                # sunlit upper-left crown, plus a softer secondary highlight for
                # a fuller, rounder canopy
                pygame.draw.circle(surf, light_c, (sx - ri(9 * s), cy - ri(8 * s)), max(1, ri(6 * s)))
                pygame.draw.circle(surf, lerp_color(main_c, light_c, 0.55),
                                   (sx + ri(7 * s), cy - ri(3 * s)), max(1, ri(4 * s)))
                # gentle ambient shade along the underside of the canopy
                pygame.draw.circle(surf, shade_c, (sx + ri(2 * s), cy + ri(9 * s)), max(1, ri(5 * s)))
            if accent_c and near:
                # a few designed blossom dabs instead of sprayed single pixels
                for dx, dy in ((-11, -6), (6, -11), (11, 1), (-3, 5), (2, -3)):
                    if (int(seed * 131) + dx * 3) % 7 < 4:
                        ax = clamp(sx + ri(dx * s), 0, config.W - 1)
                        ay = clamp(cy + ri(dy * s), 0, config.H - 1)
                        pygame.draw.circle(surf, accent_c, (ax, ay), max(1, ri(1.4 * s)))
        return


def draw_building(surf, kind, sx, sy, scale, fade):
    sx, sy = ri(sx), ri(sy)
    s = scale * config.SC
    if s <= 0:
        return
    col = _haze(fade)
    if scale >= 0.16:
        sh = lerp_color(ground_color_at(sy), GROUND_DEEP, 0.5 * (1.0 - fade))
        pygame.draw.ellipse(surf, sh, (sx - ri(15 * s), sy - ri(6 * s), max(1, ri(30 * s)), max(1, ri(12 * s))))

    if kind == "post":
        ph = ri(50 * s)
        pw = max(1, ri(6 * s))
        pygame.draw.rect(surf, col((150, 110, 74)), (sx - pw // 2, sy - ph, pw, ph))
        pygame.draw.rect(surf, col((120, 84, 56)), (sx - pw // 2, sy - ph, max(1, pw // 3), ph))
        bw, bh = ri(34 * s), ri(20 * s)
        by = sy - ph
        pygame.draw.rect(surf, col((206, 160, 108)), (sx - bw // 2, by, max(1, bw), max(1, bh)))
        pygame.draw.rect(surf, col((150, 110, 74)), (sx - bw // 2, by, max(1, bw), max(1, bh)), max(1, ri(1.4 * s)))
        if s > 0.4:
            for ly in (6, 11, 16):
                pygame.draw.line(surf, col((150, 110, 74)),
                                 (sx - bw // 2 + ri(4 * s), by + ri(ly * s)),
                                 (sx + bw // 2 - ri(5 * s), by + ri(ly * s)), max(1, ri(1 * s)))
