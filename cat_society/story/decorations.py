"""Cozy, placeable shop decorations.

Decorations are small world objects drawn with the same flat painterly shapes as
Bal's shop. They are deliberately data-driven so the travelling merchant can
rotate a broad stock without adding one-off menu code for every item.
"""

import math

import pygame

from .. import config
from ..projection import project
from ..utils import ri


DECORATIONS = {
    "round_rug": dict(name="Round Woven Rug", price=28, kind="rug", color=(198, 116, 104), desc="A warm rug for the shop entrance."),
    "moss_rug": dict(name="Moss Green Rug", price=30, kind="rug", color=(105, 143, 104), desc="A soft green rug with a stitched edge."),
    "flower_box": dict(name="Flower Box", price=34, kind="flowers", color=(231, 144, 157), desc="A wooden box full of tiny flowers."),
    "sunflower_pot": dict(name="Sunflower Pot", price=38, kind="pot", color=(241, 190, 91), desc="A cheerful pot for a sunny corner."),
    "bluebell_pot": dict(name="Bluebell Pot", price=38, kind="pot", color=(132, 153, 210), desc="A cool blue flower pot."),
    "small_bench": dict(name="Little Waiting Bench", price=72, kind="bench", color=(165, 111, 67), desc="A cozy bench. Clients wait a little longer.", effect="patience"),
    "cushion_pile": dict(name="Cushion Pile", price=42, kind="cushions", color=(215, 141, 157), desc="Soft cushions in three warm colors."),
    "lantern_post": dict(name="Golden Lantern Post", price=58, kind="lantern", color=(244, 184, 92), desc="A warm shop light that glows at night."),
    "paper_lantern": dict(name="Paper Lantern", price=48, kind="paper_lantern", color=(239, 154, 126), desc="A small hanging lantern on a wooden stand."),
    "wind_chime": dict(name="Wind Chime", price=46, kind="chime", color=(165, 197, 204), desc="A quiet chime for the breeze."),
    "music_sign": dict(name="Painted Music Sign", price=54, kind="sign", color=(223, 164, 102), desc="A hand-painted sign with a music note."),
    "record_crate": dict(name="Record Crate", price=40, kind="crate", color=(143, 95, 60), desc="A little crate of sleeves and records."),
    "tea_table": dict(name="Tea Table", price=64, kind="table", color=(171, 113, 68), desc="A tiny table for tea and waiting clients."),
    "garden_stones": dict(name="Garden Stepping Stones", price=24, kind="stones", color=(158, 153, 143), desc="Three smooth stones for a path."),
    "festival_flags": dict(name="Festival Flags", price=66, kind="flags", color=(220, 122, 126), desc="A short string of colorful cloth flags."),
    "bird_bath": dict(name="Bird Bath", price=78, kind="birdbath", color=(149, 169, 166), desc="A shallow stone bath for small visitors."),
    "tiny_pond": dict(name="Tiny Garden Pond", price=105, kind="pond", color=(102, 164, 184), desc="A small reflective pond ringed with stones."),
    "music_statue": dict(name="Little Music Cat Statue", price=96, kind="statue", color=(215, 188, 151), desc="A small stone cat holding a note."),
    "glow_jars": dict(name="Glowing Sound Jars", price=88, kind="jars", color=(177, 205, 159), desc="Three jars that glow softly at night."),
    "striped_awning": dict(name="Striped Side Awning", price=120, kind="awning", color=(210, 126, 115), desc="A small shaded corner beside the shop."),
}


def definition(item_id):
    row = DECORATIONS.get(item_id)
    if row is None:
        return None
    out = dict(row)
    out["id"] = item_id
    return out


def all_items():
    return [definition(k) for k in sorted(DECORATIONS)]


class DecorationManager:
    """Owns placement preview, persisted placed objects and world drawing."""

    def __init__(self, story_state):
        self.state = story_state
        self.placing = None
        self.rotation = 0
        self.preview = None

    def inventory_count(self, item_id):
        owned = int(self.state.decorations_owned.get(item_id, 0))
        placed = sum(1 for rec in self.state.decorations_placed if rec.get("id") == item_id)
        return max(0, owned - placed)

    def begin(self, item_id):
        if definition(item_id) is None or self.inventory_count(item_id) <= 0:
            return False
        self.placing = item_id
        self.rotation = 0
        self.preview = None
        return True

    def cancel(self):
        self.placing = None
        self.preview = None

    def rotate(self):
        self.rotation = (self.rotation + 1) % 4

    def update_preview(self, game, shop):
        if self.placing is None:
            self.preview = None
            return
        x = game.cat.x
        z = game.cat.z + 45.0
        x, z = game.water.nearest_dry(x, z)
        ok = math.hypot(x - shop.x, z - shop.z) <= 520.0
        if game.water.depth_at(x, z)[0] > 0.02:
            ok = False
        for r, wx, wz in game.world.solids_near(x, z):
            if math.hypot(wx - x, wz - z) < r + 28.0:
                ok = False
                break
        if ok:
            for r, wx, wz in shop.solids_near(x, z):
                if math.hypot(wx - x, wz - z) < r + 22.0:
                    ok = False
                    break
        if ok:
            for rec in self.state.decorations_placed:
                if math.hypot(float(rec.get("x", 0)) - x,
                              float(rec.get("z", 0)) - z) < 44.0:
                    ok = False
                    break
        self.preview = (x, z, ok)

    def place(self):
        if self.placing is None or self.preview is None or not self.preview[2]:
            return False, "Choose a clear place near the shop."
        if self.inventory_count(self.placing) <= 0:
            self.cancel()
            return False, "That decoration is no longer in storage."
        x, z, _ = self.preview
        self.state.decorations_placed.append({
            "id": self.placing, "x": round(float(x), 2), "z": round(float(z), 2),
            "rotation": int(self.rotation),
        })
        name = definition(self.placing)["name"]
        self.state.save()
        self.cancel()
        return True, "%s placed." % name

    def remove_nearest(self, x, z, radius=65.0):
        if not self.state.decorations_placed:
            return None
        rec = min(self.state.decorations_placed,
                  key=lambda r: math.hypot(float(r.get("x", 0)) - x,
                                           float(r.get("z", 0)) - z))
        if math.hypot(float(rec.get("x", 0)) - x, float(rec.get("z", 0)) - z) > radius:
            return None
        self.state.decorations_placed.remove(rec)
        self.state.save()
        return definition(rec.get("id"))

    def nearest(self, x, z, radius=65.0):
        """Return the nearest placed decoration without changing the save."""
        if not self.state.decorations_placed:
            return None
        rec = min(self.state.decorations_placed,
                  key=lambda row: math.hypot(float(row.get("x", 0)) - x,
                                             float(row.get("z", 0)) - z))
        distance = math.hypot(float(rec.get("x", 0)) - x,
                              float(rec.get("z", 0)) - z)
        return rec if distance <= radius else None

    def patience_bonus(self):
        placed = {r.get("id") for r in self.state.decorations_placed}
        return 0.18 if "small_bench" in placed else 0.0

    def light_sources(self, game):
        if game.night_strength <= 0.02:
            return []
        out = []
        for rec in self.state.decorations_placed:
            item = definition(rec.get("id"))
            if not item or item["kind"] not in ("lantern", "paper_lantern", "jars"):
                continue
            pr = project(float(rec.get("x", 0)), float(rec.get("z", 0)), game.cam)
            if pr is not None:
                out.append((pr[0], pr[1] - 8, 38 if item["kind"] != "jars" else 30,
                            item["color"], 0.95))
        return out

    def world_drawables(self, game):
        out = []
        rows = list(self.state.decorations_placed)
        if self.placing is not None and self.preview is not None:
            rows.append({"id": self.placing, "x": self.preview[0], "z": self.preview[1],
                         "rotation": self.rotation, "preview": True, "valid": self.preview[2]})
        for rec in rows:
            pr = project(float(rec.get("x", 0)), float(rec.get("z", 0)), game.cam)
            if pr is None:
                continue
            sx, sy, scale = pr
            if scale <= 0.10:
                continue
            item = definition(rec.get("id"))
            if item is None:
                continue
            preview = bool(rec.get("preview"))
            valid = bool(rec.get("valid", True))
            rot = int(rec.get("rotation", 0))
            out.append((sy + 0.3, 40, lambda surf, a=(sx, sy, scale, item, rot, preview, valid, game.time):
                        draw_decoration(surf, *a)))
        return out

    def upgrade_world_drawables(self, game, shop):
        """Show installed upgrades as small physical additions to the shop."""
        if shop is None or shop.x is None or shop.z is None:
            return []
        positions = {
            "request_board": (-116.0, -52.0),
            "listening_corner": (116.0, -44.0),
            "sound_cabinet": (-108.0, 23.0),
            "delivery_shelf": (106.0, 18.0),
            "larger_counter": (58.0, -72.0),
        }
        out = []
        for upgrade_id, (dx, dz) in positions.items():
            if not self.state.upgrades.get(upgrade_id):
                continue
            pr = project(shop.x + dx, shop.z + dz, game.cam)
            if pr is None:
                continue
            sx, sy, scale = pr
            if scale <= 0.10:
                continue
            out.append((sy + 0.25, 40,
                        lambda surf, a=(sx, sy, scale, upgrade_id, game.time):
                        draw_shop_upgrade(surf, *a)))
        return out


def draw_decoration(surf, sx, sy, scale, item, rotation=0, preview=False, valid=True, t=0.0):
    s = max(0.12, scale * config.SC)
    kind = item["kind"]
    col = item["color"] if (not preview or valid) else (190, 105, 100)
    dark = tuple(max(35, int(c * .62)) for c in col)
    light = tuple(min(255, int(c + (255 - c) * .35)) for c in col)
    alpha = 145 if preview else 255
    layer = pygame.Surface((140, 110), pygame.SRCALPHA)
    x, y = 70, 88
    q = lambda v: max(1, ri(v * s))

    def rect(color, box, radius=0, width=0):
        pygame.draw.rect(layer, (*color, alpha), tuple(ri(v) for v in box), width,
                         border_radius=max(0, ri(radius)))
    def ellipse(color, box, width=0):
        pygame.draw.ellipse(layer, (*color, alpha), tuple(ri(v) for v in box), width)
    def circle(color, pos, rad, width=0):
        pygame.draw.circle(layer, (*color, alpha), (ri(pos[0]), ri(pos[1])), max(1, ri(rad)), width)

    if kind == "rug":
        ellipse(dark, (x-30*s, y-10*s, 60*s, 20*s))
        ellipse(col, (x-28*s, y-9*s, 56*s, 17*s))
        ellipse(light, (x-19*s, y-5*s, 38*s, 9*s), max(1, q(1)))
    elif kind in ("flowers", "pot"):
        rect((137, 91, 55), (x-16*s, y-15*s, 32*s, 17*s), 3*s)
        for i in (-10, -4, 3, 10):
            pygame.draw.line(layer, (77, 126, 78, alpha), (ri(x+i*s), ri(y-14*s)),
                             (ri(x+i*s), ri(y-29*s-abs(i)*.2*s)), q(2))
            circle(col if i % 2 else light, (x+i*s, y-31*s-abs(i)*.2*s), 4*s)
    elif kind == "bench":
        rect(dark, (x-29*s, y-15*s, 58*s, 9*s), 3*s)
        rect(col, (x-31*s, y-28*s, 62*s, 12*s), 3*s)
        pygame.draw.line(layer, (*dark, alpha), (ri(x-23*s), ri(y-7*s)), (ri(x-25*s), ri(y+2*s)), q(4))
        pygame.draw.line(layer, (*dark, alpha), (ri(x+23*s), ri(y-7*s)), (ri(x+25*s), ri(y+2*s)), q(4))
    elif kind == "cushions":
        for dx, dy, c in ((-13, -7, col), (3, -9, light), (-2, -20, (202, 169, 112))):
            rect(c, (x+dx*s, y+dy*s, 25*s, 13*s), 6*s)
    elif kind in ("lantern", "paper_lantern"):
        pygame.draw.line(layer, (*dark, alpha), (ri(x), ri(y+2*s)), (ri(x), ri(y-48*s)), q(4))
        pygame.draw.line(layer, (*dark, alpha), (ri(x), ri(y-46*s)), (ri(x+15*s), ri(y-46*s)), q(3))
        glow = 2.0 + math.sin(t*2.1)*.5
        if kind == "lantern":
            rect(dark, (x+7*s, y-45*s, 18*s, 22*s), 3*s)
            rect(light, (x+10*s, y-42*s, 12*s, 15*s), 3*s)
        else:
            ellipse(light, (x+5*s, y-47*s, 24*s, 25*s))
            pygame.draw.line(layer, (*dark, alpha), (ri(x+17*s), ri(y-45*s)), (ri(x+17*s), ri(y-24*s)), q(1))
    elif kind == "chime":
        pygame.draw.line(layer, (*dark, alpha), (ri(x), ri(y)), (ri(x), ri(y-45*s)), q(3))
        pygame.draw.line(layer, (*dark, alpha), (ri(x), ri(y-43*s)), (ri(x+19*s), ri(y-43*s)), q(2))
        for i in range(3):
            xx=x+(12+i*6)*s
            pygame.draw.line(layer, (*dark, alpha), (ri(xx), ri(y-39*s)), (ri(xx), ri(y-(18+i*3)*s)), q(1))
            circle(col, (xx, y-(16+i*3)*s), 2.5*s)
    elif kind == "sign":
        pygame.draw.line(layer, (*dark, alpha), (ri(x), ri(y)), (ri(x), ri(y-42*s)), q(4))
        rect(col, (x-24*s, y-48*s, 48*s, 26*s), 5*s)
        circle(light, (x, y-35*s), 5*s)
        pygame.draw.line(layer, (*dark, alpha), (ri(x), ri(y-41*s)), (ri(x), ri(y-28*s)), q(2))
    elif kind == "crate":
        rect(dark, (x-23*s, y-22*s, 46*s, 24*s), 2*s)
        rect(col, (x-20*s, y-19*s, 40*s, 18*s), 1*s)
        for i in range(4):
            rect((229-i*8, 207-i*5, 174-i*4), (x-16*s+i*8*s, y-28*s-i%2*4*s, 6*s, 18*s), 1*s)
    elif kind == "table":
        ellipse(col, (x-25*s, y-27*s, 50*s, 18*s))
        pygame.draw.line(layer, (*dark, alpha), (ri(x), ri(y-11*s)), (ri(x), ri(y+1*s)), q(5))
        circle(light, (x-5*s, y-23*s), 5*s)
    elif kind == "stones":
        for dx, dy, sc in ((-20, 0, 1), (0, -7, .8), (20, 1, .95)):
            ellipse(dark, (x+(dx-11*sc)*s, y+(dy-5*sc)*s, 22*sc*s, 10*sc*s))
            ellipse(col, (x+(dx-10*sc)*s, y+(dy-6*sc)*s, 20*sc*s, 8*sc*s))
    elif kind == "flags":
        pygame.draw.line(layer, (*dark, alpha), (ri(x-32*s), ri(y-42*s)), (ri(x+32*s), ri(y-35*s)), q(2))
        for i, c in enumerate((col, (238,188,91), (123,167,151), (151,139,203), light)):
            xx=x+(-27+i*13)*s
            pygame.draw.polygon(layer, (*c, alpha), [(ri(xx),ri(y-41*s+i*.4*s)),(ri(xx+9*s),ri(y-40*s+i*.4*s)),(ri(xx+4*s),ri(y-27*s+i*.4*s))])
    elif kind == "birdbath":
        ellipse(dark, (x-24*s, y-25*s, 48*s, 14*s))
        ellipse(col, (x-22*s, y-27*s, 44*s, 12*s))
        ellipse((118,174,193), (x-17*s, y-24*s, 34*s, 7*s))
        rect(dark, (x-4*s, y-13*s, 8*s, 15*s), 2*s)
    elif kind == "pond":
        ellipse(dark, (x-35*s, y-13*s, 70*s, 22*s))
        ellipse(col, (x-31*s, y-11*s, 62*s, 17*s))
        ellipse(light, (x-18*s, y-7*s, 35*s, 7*s))
    elif kind == "statue":
        rect(dark, (x-14*s, y-10*s, 28*s, 12*s), 3*s)
        circle(col, (x, y-25*s), 11*s)
        pygame.draw.polygon(layer, (*col, alpha), [(ri(x-9*s),ri(y-31*s)),(ri(x-4*s),ri(y-45*s)),(ri(x+1*s),ri(y-32*s))])
        pygame.draw.polygon(layer, (*col, alpha), [(ri(x+2*s),ri(y-32*s)),(ri(x+8*s),ri(y-44*s)),(ri(x+10*s),ri(y-29*s))])
        circle(dark, (x-4*s, y-25*s), 1.5*s); circle(dark, (x+4*s, y-25*s), 1.5*s)
    elif kind == "jars":
        for dx, hh in ((-13,20),(0,27),(14,17)):
            rect(dark, (x+(dx-5)*s, y-hh*s, 10*s, hh*s), 3*s)
            rect(light, (x+(dx-3)*s, y-(hh-3)*s, 6*s, (hh-6)*s), 3*s)
    elif kind == "awning":
        pygame.draw.line(layer, (*dark, alpha), (ri(x-28*s),ri(y)), (ri(x-28*s),ri(y-46*s)), q(4))
        pygame.draw.line(layer, (*dark, alpha), (ri(x+28*s),ri(y)), (ri(x+28*s),ri(y-46*s)), q(4))
        pygame.draw.polygon(layer, (*col,alpha), [(ri(x-34*s),ri(y-46*s)),(ri(x+34*s),ri(y-46*s)),(ri(x+25*s),ri(y-30*s)),(ri(x-25*s),ri(y-30*s))])
        for i in range(-2,3,2):
            pygame.draw.line(layer, (*light,alpha), (ri(x+i*10*s),ri(y-45*s)), (ri(x+i*8*s),ri(y-31*s)), q(3))

    if preview:
        pygame.draw.circle(layer, ((94, 170, 105, 180) if valid else (198, 95, 88, 180)), (x, y+3), max(5, q(7)), max(1, q(2)))
    surf.blit(layer, (ri(sx-70), ri(sy-88)))


def draw_shop_upgrade(surf, sx, sy, scale, upgrade_id, t=0.0):
    """Draw one restrained shop fixture in the existing cozy prop language."""
    s = max(0.12, scale * config.SC)
    layer = pygame.Surface((150, 120), pygame.SRCALPHA)
    x, y = 75, 98
    wood = (155, 102, 62)
    wood_d = (104, 70, 49)
    cream = (240, 221, 183)
    green = (106, 148, 108)
    blue = (126, 158, 190)
    gold = (224, 169, 86)
    q = lambda value: max(1, ri(value * s))

    def rect(color, box, radius=0, width=0):
        pygame.draw.rect(layer, color, tuple(ri(v) for v in box), width,
                         border_radius=max(0, ri(radius)))

    def line(color, p1, p2, width=2):
        pygame.draw.line(layer, color, (ri(p1[0]), ri(p1[1])),
                         (ri(p2[0]), ri(p2[1])), q(width))

    if upgrade_id == "request_board":
        line(wood_d, (x - 19*s, y), (x - 19*s, y - 49*s), 4)
        line(wood_d, (x + 19*s, y), (x + 19*s, y - 49*s), 4)
        rect(wood_d, (x - 30*s, y - 57*s, 60*s, 40*s), 5*s)
        rect(cream, (x - 27*s, y - 54*s, 54*s, 34*s), 4*s)
        for i, width in enumerate((34, 41, 28)):
            line((137, 119, 91), (x - width*.5*s, y - (45-i*9)*s),
                 (x + width*.5*s, y - (45-i*9)*s), 1)
        pygame.draw.circle(layer, gold, (ri(x+18*s), ri(y-49*s)), q(3))
    elif upgrade_id == "listening_corner":
        rect(wood_d, (x - 34*s, y - 19*s, 68*s, 12*s), 4*s)
        rect(wood, (x - 37*s, y - 34*s, 74*s, 16*s), 5*s)
        rect((205, 133, 148), (x - 29*s, y - 30*s, 25*s, 12*s), 6*s)
        rect(blue, (x + 2*s, y - 30*s, 27*s, 12*s), 6*s)
        line(wood_d, (x - 28*s, y - 7*s), (x - 29*s, y+2*s), 4)
        line(wood_d, (x + 28*s, y - 7*s), (x + 29*s, y+2*s), 4)
        pygame.draw.circle(layer, gold, (ri(x), ri(y-45*s)), q(7), q(2))
        pygame.draw.circle(layer, cream, (ri(x), ri(y-45*s)), q(3))
    elif upgrade_id == "sound_cabinet":
        rect(wood_d, (x - 28*s, y - 61*s, 56*s, 63*s), 5*s)
        rect(wood, (x - 24*s, y - 57*s, 48*s, 55*s), 3*s)
        for yy in (y-42*s, y-24*s):
            line(wood_d, (x - 22*s, yy), (x + 22*s, yy), 3)
        for row_y, colors in ((y-50*s, (green, blue, gold)),
                              (y-32*s, ((197, 126, 144), cream, green)),
                              (y-14*s, (blue, gold, (177, 137, 194)))):
            for i, color in enumerate(colors):
                pygame.draw.circle(layer, color,
                                   (ri(x + (-13+i*13)*s), ri(row_y)), q(4))
    elif upgrade_id == "delivery_shelf":
        line(wood_d, (x - 31*s, y), (x - 31*s, y - 49*s), 4)
        line(wood_d, (x + 31*s, y), (x + 31*s, y - 49*s), 4)
        rect(wood, (x - 36*s, y - 49*s, 72*s, 8*s), 3*s)
        rect(wood, (x - 36*s, y - 25*s, 72*s, 8*s), 3*s)
        for dx, color in ((-22, green), (-7, blue), (9, gold), (23, (204, 133, 148))):
            rect(color, (x+(dx-5)*s, y-40*s, 10*s, 13*s), 3*s)
        rect(cream, (x - 20*s, y - 17*s, 40*s, 12*s), 3*s)
        line((143, 111, 80), (x - 12*s, y - 11*s), (x + 12*s, y - 11*s), 1)
    elif upgrade_id == "larger_counter":
        rect(wood_d, (x - 40*s, y - 25*s, 80*s, 27*s), 4*s)
        rect(wood, (x - 42*s, y - 31*s, 84*s, 11*s), 4*s)
        rect(cream, (x - 22*s, y - 20*s, 44*s, 14*s), 3*s)
        pygame.draw.circle(layer, green, (ri(x-11*s), ri(y-13*s)), q(3))
        pygame.draw.circle(layer, blue, (ri(x), ri(y-13*s)), q(3))
        pygame.draw.circle(layer, gold, (ri(x+11*s), ri(y-13*s)), q(3))

    surf.blit(layer, (ri(sx - 75), ri(sy - 98)))
