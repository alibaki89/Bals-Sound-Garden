"""A warm bottom-of-screen conversation bar with real choices.

Dialogue is intentionally independent from client logic. A caller supplies a
speaker, species portrait, pages and optional choices; the overlay handles the
typewriter rhythm, keyboard/mouse navigation and returns the selected choice.

The portrait shown in the box is now a literal in-game style screenshot stored
per species.  We prefer those framed meadow photos over redrawing a separate
icon so the dialogue face always matches the world look.
"""

from pathlib import Path

import pygame

from .. import config, ui


_PORTRAIT_CACHE = {}
_PHOTO_DIR = Path(__file__).resolve().parents[1] / "assets" / "dialogue_photos"


def _palette_key(palette):
    if not palette:
        return None
    return tuple(sorted((str(key), tuple(value) if isinstance(value, (tuple, list)) else value)
                        for key, value in palette.items()))


def _fit_snapshot(source, size):
    """Fit a literal entity screenshot into the dialogue portrait.

    The whole rendered creature is kept in frame with breathing room.  This is
    intentionally not a face redraw or an aggressive head crop: it is the same
    sprite the player sees in the world, shown from an ordinary game distance.
    """
    target = max(8, int(size))
    out = pygame.Surface((target, target), pygame.SRCALPHA)
    bounds = source.get_bounding_rect(min_alpha=8)
    if bounds.w <= 0 or bounds.h <= 0:
        return out
    image = source.subsurface(bounds).copy()
    margin = max(4, int(target * 0.10))
    room_w = max(1, target - margin * 2)
    room_h = max(1, target - margin * 2)
    scale = min(room_w / float(image.get_width()), room_h / float(image.get_height()))
    # Nearest-neighbour scaling preserves the exact world pixels.
    fitted = pygame.transform.scale(
        image,
        (max(1, int(round(image.get_width() * scale))),
         max(1, int(round(image.get_height() * scale)))),
    )
    rect = fitted.get_rect(midbottom=(target // 2, target - margin))
    out.blit(fitted, rect)
    return out


def _load_species_photo(species, size):
    """Load a prepared meadow screenshot for the species when available.

    These transparent images are cropped from literal in-game Explore captures.
    Each keeps the exact entity pixels while presenting a consistent head and
    face scale in the dialogue box.
    """
    species = str(species or 'dog').lower()
    key = ('photo', species, int(size))
    cached = _PORTRAIT_CACHE.get(key)
    if cached is not None:
        return cached
    path = _PHOTO_DIR / f'{species}.png'
    if not path.exists():
        return None
    try:
        image = pygame.image.load(str(path)).convert_alpha()
    except Exception:
        return None
    target = max(8, int(size))
    margin = max(4, int(target * 0.08))
    room = max(1, target - margin * 2)
    fitted_inner = pygame.transform.scale(image, (room, room))
    fitted = pygame.Surface((target, target), pygame.SRCALPHA)
    fitted.blit(fitted_inner, fitted_inner.get_rect(center=(target // 2, target // 2)))
    _PORTRAIT_CACHE[key] = fitted
    return fitted




def _render_entity_snapshot(entity, size, palette=None):
    """Capture an actual Cat/Animal entity with its normal world renderer."""
    target = max(8, int(size))
    # Render first at the low-resolution scale used by the meadow, then enlarge
    # those pixels.  This is why the portrait now looks exactly like the actor
    # walking outside the shop instead of like separate icon artwork.
    low = pygame.Surface((128, 112), pygame.SRCALPHA)
    ground = (64, 101)
    if hasattr(entity, "spec"):
        ds = config.SC * float(entity.spec.draw_scale)
        entity.draw(low, ground[0], ground[1], ds, 1.0,
                    swim=0.0, fade=0.0, draw_shadow=False)
    else:
        entity.draw(low, ground[0], ground[1], config.SC,
                    draw_shadow=False, swim=0.0, palette=palette)
    return _fit_snapshot(low, target)


def _fallback_entity(species):
    """Build a deterministic ordinary idle actor only when no live actor exists."""
    import random
    from ..entities.animals import Animal
    from ..entities.cat import Cat

    if species == "bal":
        cat = Cat()
        cat.facing = 1
        cat.t = 0.35
        cat.expression = "neutral"
        return cat
    animal = Animal(species, 0.0, 0.0, random.Random(712367 + sum(map(ord, species))))
    animal.facing = 1
    animal.t = 0.35
    animal.state = "idle"
    animal.mood = "neutral"
    animal.blink = False
    return animal


def _entity_portrait(species, size, entity=None, palette=None):
    """Return a meadow screenshot, preferring prepared in-game captures."""
    photo = _load_species_photo(species, size)
    if photo is not None:
        return photo
    key = None
    if entity is None:
        key = (species, int(size), _palette_key(palette))
        cached = _PORTRAIT_CACHE.get(key)
        if cached is not None:
            return cached
        entity = _fallback_entity(species)
    image = _render_entity_snapshot(entity, size, palette)
    if key is not None:
        _PORTRAIT_CACHE[key] = image
    return image


def _crop_exact_sprite(species, size, palette=None):
    """Backward-compatible name for the full in-world entity screenshot."""
    return _entity_portrait(species, size, entity=None, palette=palette)


class DialogueOverlay:
    def __init__(self):
        self.speaker = ""
        self.species = "dog"
        self.pages = []
        self.page = 0
        self.choices = []
        self.selected = 0
        self.callback = None
        self.portrait_palette = None
        self.portrait_entity = None
        self.portrait_photo = None
        self.portrait_image = None
        self.t = 0.0
        self.reveal = 0.0
        self.rects = []

    @property
    def active(self):
        return bool(self.pages)

    def open(self, speaker, species, pages, choices=None, callback=None,
             portrait_palette=None, portrait_entity=None):
        self.speaker = str(speaker)
        self.species = species or "dog"
        self.portrait_palette = portrait_palette
        self.portrait_entity = portrait_entity
        self.portrait_photo = None
        self.portrait_image = None
        self.pages = [str(p) for p in pages if str(p).strip()]
        self.page = 0
        self.choices = list(choices or [])
        self.selected = 0
        self.callback = callback
        self.t = 0.0
        self.reveal = 0.0
        self.rects = []
        pygame.mouse.set_visible(True)

    def close(self):
        self.pages = []
        self.choices = []
        self.rects = []
        self.callback = None
        self.portrait_palette = None
        self.portrait_entity = None
        self.portrait_photo = None
        self.portrait_image = None
        pygame.mouse.set_visible(False)


    def capture_world_portrait(self, surf, capture):
        """Freeze a literal crop from the already-painted game world.

        StoryScreen calls this immediately after the low-resolution world has
        been enlarged to the window and before any HUD, speech bubble, veil, or
        dialogue panel is drawn.  The result is therefore a real frame grab of
        the speaking actor in the meadow, not a second portrait illustration.
        """
        if (not self.active or self.portrait_photo is not None
                or self.portrait_entity is None or capture is None):
            return
        try:
            photo = capture(surf, self.portrait_entity)
        except Exception:
            photo = None
        if isinstance(photo, pygame.Surface) and photo.get_width() > 0 and photo.get_height() > 0:
            facing = getattr(self.portrait_entity, "facing", 1)
            if facing < 0:
                photo = pygame.transform.flip(photo, True, False)
            self.portrait_photo = photo.copy()
            self.portrait_image = None

    def update(self, dt):
        if not self.active:
            return
        self.t += dt
        self.reveal += dt * 44.0

    def _fully_revealed(self):
        return self.reveal >= len(self.pages[self.page])

    def _advance(self):
        if not self._fully_revealed():
            self.reveal = float(len(self.pages[self.page]))
            return
        if self.page + 1 < len(self.pages):
            self.page += 1
            self.reveal = 0.0
            return
        if not self.choices:
            cb = self.callback
            self.close()
            if cb:
                cb(None)

    def _choose(self, idx):
        if not self.choices:
            self._advance()
            return
        idx = max(0, min(len(self.choices) - 1, idx))
        choice = self.choices[idx]
        value = choice[1] if isinstance(choice, (tuple, list)) and len(choice) > 1 else choice
        cb = self.callback
        self.close()
        if cb:
            cb(value)

    def handle_event(self, e):
        if not self.active:
            return False
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.close()
                return True
            if self.choices and self.page == len(self.pages) - 1 and self._fully_revealed():
                if e.key in (pygame.K_UP, pygame.K_w, pygame.K_LEFT, pygame.K_a):
                    self.selected = (self.selected - 1) % len(self.choices)
                elif e.key in (pygame.K_DOWN, pygame.K_s, pygame.K_RIGHT, pygame.K_d):
                    self.selected = (self.selected + 1) % len(self.choices)
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                    self._choose(self.selected)
                else:
                    self._advance()
            else:
                self._advance()
            return True
        if e.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos):
                    self.selected = i
                    break
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos):
                    self._choose(i)
                    return True
            self._advance()
            return True
        return True

    def draw(self, surf):
        if not self.active:
            return
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        panel = pygame.Rect(S(28), h - S(238), w - S(56), S(196))
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((24, 23, 25, 48))
        surf.blit(veil, (0, 0))
        ui.draw_panel(surf, panel, fill=ui.PAPER, edge=ui.PAPER_EDGE, radius=S(15))

        portrait = pygame.Rect(panel.x + S(18), panel.y + S(22), S(112), S(112))
        ui.draw_panel(surf, portrait, fill=ui.CREAM, edge=ui.PAPER_EDGE,
                      radius=S(14), shadow=False)
        if self.portrait_image is None:
            target = max(8, portrait.w - S(10))
            # Prefer the prepared species screenshot so every dialogue uses the
            # same clear in-world framing instead of redrawn face art.  When a
            # species photo is missing we fall back to the captured live photo,
            # then to a renderer-generated snapshot.
            self.portrait_image = _load_species_photo(self.species, target)
            if self.portrait_image is None and self.portrait_photo is not None:
                self.portrait_image = pygame.transform.scale(
                    self.portrait_photo, (target, target))
            if self.portrait_image is None:
                self.portrait_image = _entity_portrait(
                    self.species, target, self.portrait_entity,
                    self.portrait_palette)
        surf.blit(self.portrait_image,
                  self.portrait_image.get_rect(center=portrait.center))

        name_box = pygame.Rect(portrait.x, portrait.bottom + S(7), portrait.w, S(28))
        ui.draw_panel(surf, name_box, fill=ui.GRASS, radius=S(7), shadow=False)
        ui.pixel_text_fit_box(surf, self.speaker.upper(), S(14),
                              name_box.inflate(-S(8), -S(4)), color=ui.CREAM,
                              min_size=S(9), center=True)

        tx = portrait.right + S(24)
        text_rect = pygame.Rect(tx, panel.y + S(22), panel.right - tx - S(22), S(90))
        full = self.pages[self.page]
        shown = full[:max(0, int(self.reveal))]
        lines = ui.wrap_lines(shown, text_rect.w, S(18))
        y = text_rect.y
        for line in lines[:5]:
            ui.pixel_text(surf, line, S(18), text_rect.x, y, color=ui.INK, bold=False)
            y += ui.pixel_line_height(S(18)) + S(5)

        self.rects = []
        ready = self.page == len(self.pages) - 1 and self._fully_revealed()
        if ready and self.choices:
            gap = S(10)
            count = len(self.choices)
            bw = max(S(122), (text_rect.w - gap * (count - 1)) // count)
            total = bw * count + gap * (count - 1)
            x = text_rect.centerx - total // 2
            by = panel.bottom - S(56)
            for i, ch in enumerate(self.choices):
                label = ch[0] if isinstance(ch, (tuple, list)) else str(ch)
                r = pygame.Rect(x + i * (bw + gap), by, bw, S(38))
                self.rects.append(r)
                active = i == self.selected or r.collidepoint(pygame.mouse.get_pos())
                ui.draw_panel(surf, r, fill=(ui.GRASS if active else ui.PAPER_DK),
                              edge=(ui.GRASS_DK if active else ui.PAPER_EDGE),
                              radius=S(8), shadow=False)
                ui.pixel_text_fit_box(surf, label.upper(), S(13), r.inflate(-S(8), -S(6)),
                                      color=(ui.CREAM if active else ui.INK),
                                      min_size=S(9), center=True)
        else:
            hint = "E OR ENTER TO CONTINUE" if self._fully_revealed() else "E OR ENTER TO SHOW TEXT"
            ui.pixel_text(surf, hint, S(11), panel.right - S(22), panel.bottom - S(25),
                          color=ui.INK_SOFT, right=True)
