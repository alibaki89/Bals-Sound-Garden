"""Shared look-and-feel for the menu / Music Maker / Your Music screens.

The exploration view keeps its low-res pixel canvas.  The menu-style screens
draw at the real window resolution so text stays crisp and clickable, but they
borrow the same warm storybook palette and a chunky monospace font so the whole
game still reads as one cozy piece.
"""

import unicodedata

import pygame

from .. import config

# ---- warm storybook palette (paper + ink + soft accents) -------------------
PAPER      = (247, 240, 224)     # main background cream
PAPER_DK   = (236, 226, 206)     # panel fill
PAPER_EDGE = (208, 192, 162)     # panel border
INK        = (74, 56, 44)        # primary text (warm dark brown)
INK_SOFT   = (120, 104, 88)      # secondary text
CREAM      = (252, 247, 236)
SHADOW     = (40, 32, 28)

GRASS      = (120, 196, 116)     # cozy green accent
GRASS_DK   = (86, 158, 96)
SKY        = (150, 200, 240)
SUN        = (255, 224, 150)
ROSE       = (232, 150, 150)
PLUM       = (200, 160, 220)

BTN        = (250, 242, 226)
BTN_HOVER  = (255, 250, 238)
BTN_EDGE   = (198, 168, 132)
BTN_DOWN   = (236, 224, 204)

GRID_LINE  = (212, 199, 172)
GRID_BAR   = (190, 174, 146)
LANE_A     = (243, 235, 218)
LANE_B     = (236, 227, 208)
PLAYHEAD   = (228, 120, 96)

# rarity glows reused from the catalog feel
RARITY_COL = {
    "common":   (176, 214, 150),
    "uncommon": (150, 206, 224),
    "rare":     (212, 168, 236),
    "secret":   (250, 224, 150),
}

_FONT_NAME = "couriernew,consolas,monospace"
_cache = {}

_PIXEL_FONT_NAME = "trebuchetms,verdana,tahoma,arial,dejavusans,sans"
_pixel_cache = {}


_TEXT_REPLACEMENTS = {
    "\u2022": "-",      # bullet
    "\u2605": "*",      # filled star
    "\u2606": "-",      # empty star
    "\u25cf": "o",      # filled circle
    "\u00d7": "X",      # multiplication / close
    "\u2212": "-",      # mathematical minus
    "\u2014": "-",      # em dash
    "\u2013": "-",      # en dash
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
}


def safe_text(value):
    """Return display text that every bundled system font can render.

    A few decorative Unicode symbols looked like empty square boxes on some
    Windows font installations.  The game does not need those symbols to
    communicate, so all shared UI rendering now converts them to simple ASCII
    before measuring and drawing.  This keeps layout measurements and pixels in
    agreement and prevents tofu rectangles anywhere that uses the UI helpers.
    """
    text = str(value)
    for source, replacement in _TEXT_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    # Keep ordinary accented names readable when possible, but never hand an
    # unsupported symbol to a platform-dependent SysFont fallback.
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text


def _pixel_font_parts(size, bold=True):
    """Return the readable display font used by in-game UI text.

    Earlier versions upscaled a very small console font to force a heavier
    pixel look.  That matched the vibe, but it reduced legibility and made line
    fitting harder across menus.  We now use a warmer readable screen font at
    the requested size so the game still feels cozy while remaining clean and
    presentable.
    """
    size = max(8, int(size))
    key = (size, bool(bold))
    f = _pixel_cache.get(key)
    if f is None:
        f = pygame.font.SysFont(_PIXEL_FONT_NAME, size, bold=bold)
        _pixel_cache[key] = f
    return f


def pixel_render(s, size, color=INK, bold=True):
    """Render the game's primary readable UI text surface."""
    f = _pixel_font_parts(size, bold)
    return f.render(safe_text(s), True, color)


def pixel_measure(s, size, bold=True):
    return _pixel_font_parts(size, bold).size(safe_text(s))


def pixel_line_height(size, bold=True):
    return pixel_render("Ag", size, INK, bold).get_height()


def fit_size(s, base_size, max_width, min_size=9, bold=True, measure=pixel_measure):
    size = max(min_size, int(base_size))
    while size > min_size and measure(s, size, bold)[0] > max_width:
        size -= 1
    return size


def wrap_lines(text, a, b, pixel=False, bold=False, measure=None):
    """Wrap text to a width.

    Supports both ``wrap_lines(text, max_width, size)`` and the earlier helper
    shape ``wrap_lines(text, size, max_width, pixel=True/False)`` used by the
    regression tests.
    """
    if a <= 40 and b >= 40:
        size, max_width = a, b
    else:
        max_width, size = a, b
    if measure is None:
        measure = pixel_measure if pixel or True else pixel_measure
    words = safe_text(text).split()
    if not words:
        return [""]
    lines = []
    cur = words[0]
    for word in words[1:]:
        trial = cur + " " + word
        if measure(trial, size, bold)[0] <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def draw_wrapped(surf, text_value, size, rect, color=INK_SOFT, bold=False,
                 line_gap=4, max_lines=None, center=False):
    rect = pygame.Rect(rect)
    lines = wrap_lines(text_value, rect.w, size, bold=bold)
    if max_lines is not None:
        lines = lines[:max_lines]
    lh = pixel_line_height(size, bold) + line_gap
    y = rect.y
    for line in lines:
        if y + lh > rect.bottom + line_gap:
            break
        if center:
            pixel_text(surf, line, size, rect.centerx, y, color=color,
                       center=True, bold=bold)
        else:
            pixel_text(surf, line, size, rect.x, y, color=color, bold=bold)
        y += lh
    return y


def pixel_text(surf, s, size, x, y, color=INK, center=False, right=False,
               bold=True, shadow=False):
    """Blit the game's cozy pixel text and return its final rectangle."""
    s = safe_text(s)
    img = pixel_render(s, size, color, bold)
    r = img.get_rect()
    if center:
        r.midtop = (x, y)
    elif right:
        r.topright = (x, y)
    else:
        r.topleft = (x, y)
    if shadow:
        sh = pixel_render(s, size, (*SHADOW, 255), bold)
        surf.blit(sh, r.move(max(1, size // 16), max(1, size // 16)))
    surf.blit(img, r)
    return r


def pixel_text_center_box(surf, s, size, rect, color=INK, bold=True,
                          shadow=False):
    rect = pygame.Rect(rect)
    size = fit_size(str(s), size, max(10, rect.w - 8),
                    min_size=8, bold=bold)
    img = pixel_render(s, size, color, bold)
    r = img.get_rect(center=rect.center)
    if shadow:
        sh = pixel_render(s, size, (*SHADOW, 255), bold)
        surf.blit(sh, r.move(max(1, size // 16), max(1, size // 16)))
    surf.blit(img, r)
    return r


def pixel_text_fit_box(surf, s, size, rect, color=INK, bold=True, min_size=9, shadow=False,
                       center=True, right=False):
    rect = pygame.Rect(rect)
    fs = fit_size(str(s), size, max(10, rect.w - 8), min_size=min_size, bold=bold)
    if center:
        return pixel_text_center_box(surf, s, fs, rect, color=color, bold=bold, shadow=shadow)
    y = rect.y + max(0, (rect.h - pixel_line_height(fs, bold)) // 2)
    if right:
        return pixel_text(surf, s, fs, rect.right, y, color=color, bold=bold, right=True, shadow=shadow)
    return pixel_text(surf, s, fs, rect.x, y, color=color, bold=bold, shadow=shadow)


def font(size, bold=True):
    """A cached chunky monospace font at the given pixel size."""
    key = (size, bold)
    f = _cache.get(key)
    if f is None:
        f = pygame.font.SysFont(_FONT_NAME, size, bold=bold)
        _cache[key] = f
    return f


def scaled(win_h, base):
    """Scale UI from the stable interface height chosen by the display shell.

    ``win_h`` remains in the signature for compatibility, but fullscreen keeps
    ``config.UI_H`` at the previous windowed height so the interface does not
    zoom merely because F11 changed the display mode.
    """
    effective_h = getattr(config, "UI_H", win_h)
    return max(8, int(round(base * effective_h / 1080.0)))


# ---- drawing helpers -------------------------------------------------------
def draw_panel(surf, rect, fill=PAPER_DK, edge=PAPER_EDGE, radius=10, shadow=True,
               sheen=True):
    """A soft cream panel with a drop shadow, border and top sheen line."""
    rect = pygame.Rect(rect)
    if shadow:
        sh = pygame.Surface((rect.w + 8, rect.h + 8), pygame.SRCALPHA)
        pygame.draw.rect(sh, (*SHADOW, 60), sh.get_rect(), border_radius=radius + 2)
        surf.blit(sh, (rect.x - 2, rect.y + 4))
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    if sheen:
        line = pygame.Rect(rect.x + radius, rect.y + 2, rect.w - radius * 2, 2)
        pygame.draw.rect(surf, CREAM, line, border_radius=2)
    pygame.draw.rect(surf, edge, rect, width=2, border_radius=radius)


def text(surf, s, size, x, y, color=INK, center=False, right=False, bold=True,
         shadow=False):
    """Blit a line of text; returns its rect."""
    s = safe_text(s)
    f = font(size, bold)
    if shadow:
        sh = f.render(s, False, (*SHADOW, 255))
        surf.blit(sh, (x + 1 - (sh.get_width() if right else sh.get_width() // 2 if center else 0) + 1,
                       y + 1))
    img = f.render(s, False, color)
    r = img.get_rect()
    if center:
        r.midtop = (x, y)
    elif right:
        r.topright = (x, y)
    else:
        r.topleft = (x, y)
    surf.blit(img, r)
    return r


def text_center_box(surf, s, size, rect, color=INK, bold=True):
    """Center a line of text inside a rect."""
    s = safe_text(s)
    f = font(size, bold)
    img = f.render(s, False, color)
    r = img.get_rect(center=pygame.Rect(rect).center)
    surf.blit(img, r)
    return r


def vertical_gradient(surf, rect, top_col, bottom_col):
    """Fill a rect with a simple vertical gradient (cheap, row by row)."""
    rect = pygame.Rect(rect)
    h = max(1, rect.h)
    for i in range(h):
        t = i / h
        col = (
            int(top_col[0] + (bottom_col[0] - top_col[0]) * t),
            int(top_col[1] + (bottom_col[1] - top_col[1]) * t),
            int(top_col[2] + (bottom_col[2] - top_col[2]) * t),
        )
        pygame.draw.line(surf, col, (rect.x, rect.y + i), (rect.right, rect.y + i))
