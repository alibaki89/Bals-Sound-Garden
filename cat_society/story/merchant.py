"""A travelling tanuki merchant and a compact cozy shop window."""

import math
import random

import pygame

from .. import config, ui
from ..components import catalog
from ..entities.animals import Animal
from ..projection import project
from ..ui.icons import draw_icon
from .economy import build_stock, merchant_visits
from .decorations import definition as decor_definition


class Merchant:
    def __init__(self, story_state, collection, shop, world_seed, helper_manager):
        self.state = story_state
        self.collection = collection
        self.shop = shop
        self.world_seed = int(world_seed)
        self.helpers = helper_manager
        base_x = float(shop.x) if shop.x is not None else 0.0
        base_z = float(shop.z) if shop.z is not None else 0.0
        self.animal = Animal("tanuki", base_x + 185.0, base_z - 38.0,
                             random.Random(world_seed ^ 0x7A11))
        self.animal.facing = -1
        self.active = False
        self.stock = []
        self.stock_day = None
        self.bubble = ""
        self.bubble_t = 0.0

    def _set_day(self, day):
        day = int(day)
        self.active = merchant_visits(self.world_seed, day)
        if self.active and self.stock_day != day:
            sold = set(self.state.merchant_sold.get(str(day), []))
            self.stock = [item for item in build_stock(
                self.world_seed, day, self.collection, self.state)
                if "%s:%s" % (item.get("kind"), item.get("id")) not in sold]
            self.stock_day = day

    def update(self, dt, clock):
        self._set_day(clock.day)
        self.active = bool(self.shop.ready and self.active and 9 * 60 + 20 <= clock.minutes < 16 * 60 + 30)
        self.bubble_t = max(0.0, self.bubble_t - dt)
        if not self.active:
            return
        self.animal.x = self.shop.x + 185.0
        self.animal.z = self.shop.z - 38.0
        self.animal.update(dt, {"script": {"mode": "idle", "mood": "happy"}})

    def say(self, text, seconds=3.0):
        self.bubble = text
        self.bubble_t = seconds

    def near(self, cat, radius=125.0):
        return self.active and math.hypot(cat.x - self.animal.x, cat.z - self.animal.z) <= radius

    def world_drawables(self, game):
        if not self.active:
            return []
        pr = project(self.animal.x, self.animal.z, game.cam)
        if pr is None:
            return []
        sx, sy, sc = pr
        ds = sc * config.SC * self.animal.spec.draw_scale
        cart_pr = project(self.animal.x + 72.0, self.animal.z + 18.0, game.cam)
        out = [(sy, 40, lambda surf, a=(self.animal, sx, sy, ds, sc):
                a[0].draw(surf, a[1], a[2], a[3], a[4], swim=0.0, fade=0.0))]
        if cart_pr is not None:
            cx, cy, cs = cart_pr
            out.append((cy + 0.2, 40,
                        lambda surf, a=(cx, cy, cs * config.SC, game.time):
                        draw_merchant_cart(surf, *a)))
        return out

    def draw_bubble(self, surf, game):
        if not self.active or self.bubble_t <= 0.0 or not self.bubble:
            return
        pr = project(self.animal.x, self.animal.z, game.cam)
        if pr is None:
            return
        px, py = config.canvas_to_window(pr[0], pr[1] - 48 * pr[2] * config.SC)
        h = surf.get_height(); S = lambda v: ui.scaled(h, v)
        lines = ui.wrap_lines(self.bubble, S(270), S(13))[:2]
        lh = ui.pixel_line_height(S(13)) + S(2)
        bw = max(S(150), min(S(310), max(ui.pixel_measure(line, S(13))[0] for line in lines) + S(24)))
        box = pygame.Rect(0, 0, bw, S(16) + len(lines) * lh)
        box.midbottom = (int(px), int(py) - S(8))
        box.clamp_ip(pygame.Rect(S(8), S(8), surf.get_width()-S(16), surf.get_height()-S(16)))
        ui.draw_panel(surf, box, fill=ui.CREAM, edge=(216, 164, 96), radius=S(8), shadow=False)
        y = box.y + S(8)
        for line in lines:
            ui.pixel_text(surf, line, S(13), box.centerx, y, color=ui.INK, center=True, bold=False)
            y += lh

    def purchase(self, item):
        if item not in self.stock:
            return False, "That item is no longer in the cart."
        price = int(item.get("price", 0))
        if self.state.coins < price:
            return False, "Bal needs %d more coins." % (price - self.state.coins)
        kind = item.get("kind")
        item_id = item.get("id")
        if kind == "sound":
            comp = catalog.get(item_id)
            if comp is None or self.collection.owns(item_id):
                return False, "Bal already owns that sound."
            self.collection.collect(item_id)
        elif kind == "decor":
            self.state.decorations_owned[item_id] = int(self.state.decorations_owned.get(item_id, 0)) + 1
        elif kind == "upgrade":
            if self.state.upgrades.get(item_id):
                return False, "That shop upgrade is already installed."
            self.state.upgrades[item_id] = True
        elif kind == "helper":
            if self.helpers.hired(item_id):
                return False, "That helper already works with Bal."
            self.helpers.hire(item_id)
            rec = self.helpers.record(item_id)
            rec["last_paid_day"] = int(self.state.day)
            rec["on_duty"] = False
        else:
            return False, "The merchant cannot sell that item."
        self.state.coins -= price
        self.state.merchant_purchases += 1
        day_key = str(self.stock_day or self.state.day)
        sold = self.state.merchant_sold.setdefault(day_key, [])
        token = "%s:%s" % (kind, item_id)
        if token not in sold:
            sold.append(token)
        # Only recent visit records matter and this keeps the tiny save tidy.
        keep_days = sorted((int(key), key) for key in self.state.merchant_sold
                           if str(key).isdigit())[-14:]
        keep = {key for _, key in keep_days}
        self.state.merchant_sold = {
            key: value for key, value in self.state.merchant_sold.items()
            if key in keep
        }
        self.state.save()
        self.stock.remove(item)
        self.say("A good choice. I will wrap it carefully.")
        return True, "%s bought for %d coins." % (item.get("name", "Item"), price)


class MerchantOverlay:
    def __init__(self, app, merchant):
        self.app = app
        self.merchant = merchant
        self.active = False
        self.idx = 0
        self.scroll = 0
        self.rects = []
        self.message = ""
        self.message_t = 0.0

    def open(self):
        self.active = True
        self.idx = 0
        self.scroll = 0
        self.message = "Listen before buying. The cart changes on every visit."
        self.message_t = 4.0
        pygame.mouse.set_visible(True)

    def close(self):
        self.active = False
        pygame.mouse.set_visible(False)

    def update(self, dt):
        self.message_t = max(0.0, self.message_t - dt)

    def _preview(self):
        stock = self.merchant.stock
        if not stock:
            return
        item = stock[max(0, min(self.idx, len(stock)-1))]
        if item.get("kind") == "sound":
            comp = catalog.get(item.get("id"))
            if comp is not None:
                self.app.engine.preview_component(comp)
                self.message = "Playing %s." % comp["name"]
                self.message_t = 2.4
        else:
            self.message = item.get("desc", "")
            self.message_t = 3.5

    def _buy(self):
        stock = self.merchant.stock
        if not stock:
            return
        self.idx = max(0, min(self.idx, len(stock)-1))
        item = stock[self.idx]
        ok, text = self.merchant.purchase(item)
        self.message = text
        self.message_t = 4.0
        if ok:
            self.idx = max(0, min(self.idx, len(self.merchant.stock)-1))

    def handle_event(self, e):
        if not self.active:
            return False
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.close(); return True
            if e.key in (pygame.K_UP, pygame.K_w):
                self.idx = max(0, self.idx - 1); return True
            if e.key in (pygame.K_DOWN, pygame.K_s):
                self.idx = min(max(0, len(self.merchant.stock)-1), self.idx + 1); return True
            if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._buy(); return True
            if e.key == pygame.K_p:
                self._preview(); return True
        if e.type == pygame.MOUSEWHEEL:
            self.idx = max(0, min(max(0, len(self.merchant.stock)-1), self.idx - e.y))
            return True
        if e.type == pygame.MOUSEMOTION:
            for rect, action, value in self.rects:
                if rect.collidepoint(e.pos) and action == "row":
                    self.idx = value
                    break
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, action, value in self.rects:
                if not rect.collidepoint(e.pos):
                    continue
                if action == "row":
                    self.idx = value
                elif action == "buy":
                    self._buy()
                elif action == "preview":
                    self._preview()
                elif action == "close":
                    self.close()
                return True
        return True

    def draw(self, surf):
        if not self.active:
            return
        w, h = surf.get_size(); S = lambda v: ui.scaled(h, v)
        veil = pygame.Surface((w,h), pygame.SRCALPHA); veil.fill((26,23,20,180)); surf.blit(veil,(0,0))
        panel = pygame.Rect(0,0,min(w-S(36),S(900)),min(h-S(36),S(720))); panel.center=(w//2,h//2)
        ui.draw_panel(surf,panel,fill=ui.PAPER,radius=S(16))
        ui.pixel_text(surf,"POKO'S TRAVELLING CART",S(27),panel.x+S(28),panel.y+S(20),color=ui.INK)
        ui.pixel_text(surf,"COINS %d"%self.merchant.state.coins,S(16),panel.right-S(28),panel.y+S(27),color=(178,126,57),right=True)
        ui.pixel_text(surf,"P PREVIEW   ENTER BUY   ESC CLOSE",S(12),panel.x+S(30),panel.y+S(61),color=ui.INK_SOFT)
        stock=self.merchant.stock
        self.rects=[]
        list_rect=pygame.Rect(panel.x+S(24),panel.y+S(92),panel.w-S(48),panel.h-S(188))
        rows=max(1,min(8,list_rect.h//S(58)))
        first=max(0,min(self.idx-rows//2,max(0,len(stock)-rows)))
        for j,i in enumerate(range(first,min(len(stock),first+rows))):
            item=stock[i]; r=pygame.Rect(list_rect.x,list_rect.y+j*S(58),list_rect.w,S(50)); sel=i==self.idx
            ui.draw_panel(surf,r,fill=ui.CREAM if sel else ui.PAPER_DK,edge=ui.GRASS if sel else ui.PAPER_EDGE,radius=S(9),shadow=False)
            kind=item.get("kind"); icon="note" if kind=="sound" else ("crystal" if kind=="decor" else "rune")
            col=(128,174,139) if kind=="sound" else ((218,150,112) if kind=="decor" else (146,144,194))
            draw_icon(surf,r.x+S(24),r.centery,S(11),col,icon,0.0)
            ui.pixel_text_fit_box(surf,item.get("name","ITEM").upper(),S(15),pygame.Rect(r.x+S(46),r.y+S(6),r.w-S(190),S(20)),color=ui.INK,min_size=S(10),center=False)
            ui.pixel_text_fit_box(surf,item.get("desc",""),S(11),pygame.Rect(r.x+S(46),r.y+S(27),r.w-S(190),S(16)),color=ui.INK_SOFT,min_size=S(8),bold=False,center=False)
            price="%d COINS"%int(item.get("price",0)); ui.pixel_text(surf,price,S(13),r.right-S(16),r.centery-S(7),color=(175,120,55),right=True)
            self.rects.append((r,"row",i))
        if not stock:
            ui.pixel_text(surf,"The cart is sold out for today.",S(18),list_rect.centerx,list_rect.centery,color=ui.INK_SOFT,center=True)
        msg=self.message if self.message_t>0 else "Buy sounds, decorations, shop upgrades, and helper contracts."
        ui.pixel_text_fit_box(surf,msg,S(13),pygame.Rect(panel.x+S(28),panel.bottom-S(82),panel.w-S(280),S(45)),color=ui.INK_SOFT,min_size=S(9),bold=False,center=False)
        prev=pygame.Rect(panel.right-S(236),panel.bottom-S(72),S(94),S(42)); buy=pygame.Rect(panel.right-S(132),panel.bottom-S(72),S(104),S(42))
        ui.draw_panel(surf,prev,fill=ui.PAPER_DK,edge=ui.PAPER_EDGE,radius=S(8),shadow=False); ui.pixel_text_center_box(surf,"PREVIEW",S(12),prev,color=ui.INK)
        ui.draw_panel(surf,buy,fill=ui.GRASS,edge=ui.GRASS_DK,radius=S(8),shadow=False); ui.pixel_text_center_box(surf,"BUY",S(13),buy,color=ui.CREAM)
        self.rects.extend([(prev,"preview",None),(buy,"buy",None)])


def draw_merchant_cart(surf, sx, sy, scale, t=0.0):
    """A small warm wooden cart built from the game's ordinary prop shapes."""
    s = max(0.25, float(scale))
    layer = pygame.Surface((170, 125), pygame.SRCALPHA)
    x, y = 85, 102
    wood = (158, 103, 62)
    wood_d = (104, 69, 46)
    cream = (238, 215, 174)
    red = (205, 116, 106)
    green = (108, 151, 111)
    blue = (126, 157, 190)
    gold = (225, 170, 87)
    q = lambda value: max(1, int(round(value * s)))

    pygame.draw.ellipse(layer, (82, 70, 58, 55),
                        (int(x-48*s), int(y-8*s), int(96*s), int(16*s)))
    pygame.draw.rect(layer, wood_d,
                     (int(x-47*s), int(y-42*s), int(94*s), int(39*s)),
                     border_radius=q(5))
    pygame.draw.rect(layer, wood,
                     (int(x-43*s), int(y-39*s), int(86*s), int(31*s)),
                     border_radius=q(4))
    pygame.draw.line(layer, wood_d, (int(x-34*s), int(y-28*s)),
                     (int(x+34*s), int(y-28*s)), q(2))
    pygame.draw.line(layer, wood_d, (int(x-34*s), int(y-17*s)),
                     (int(x+34*s), int(y-17*s)), q(2))
    for dx in (-32, 32):
        pygame.draw.circle(layer, wood_d, (int(x+dx*s), int(y-1*s)), q(12))
        pygame.draw.circle(layer, cream, (int(x+dx*s), int(y-1*s)), q(6))
        pygame.draw.circle(layer, wood_d, (int(x+dx*s), int(y-1*s)), q(2))
    pygame.draw.line(layer, wood_d, (int(x+43*s), int(y-30*s)),
                     (int(x+67*s), int(y-8*s)), q(4))
    pygame.draw.line(layer, wood_d, (int(x-38*s), int(y-42*s)),
                     (int(x-38*s), int(y-70*s)), q(3))
    pygame.draw.line(layer, wood_d, (int(x+38*s), int(y-42*s)),
                     (int(x+38*s), int(y-70*s)), q(3))
    pygame.draw.polygon(layer, red, [
        (int(x-48*s), int(y-70*s)), (int(x+48*s), int(y-70*s)),
        (int(x+39*s), int(y-52*s)), (int(x-39*s), int(y-52*s)),
    ])
    for dx, color in ((-25, cream), (0, gold), (25, cream)):
        pygame.draw.polygon(layer, color, [
            (int(x+(dx-10)*s), int(y-69*s)),
            (int(x+(dx+10)*s), int(y-69*s)),
            (int(x+(dx+8)*s), int(y-53*s)),
            (int(x+(dx-8)*s), int(y-53*s)),
        ])
    for dx, color in ((-22, green), (0, blue), (22, gold)):
        pygame.draw.circle(layer, color, (int(x+dx*s), int(y-45*s)), q(6))
        pygame.draw.rect(layer, wood_d,
                         (int(x+(dx-5)*s), int(y-42*s), q(10), q(5)),
                         border_radius=q(2))
    surf.blit(layer, (int(round(sx-85)), int(round(sy-102))))
