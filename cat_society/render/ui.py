"""The tiny on-screen HUD: the title plate and the controls hint strip."""

import pygame

from .. import config


def draw_hud(surf, font):
    """Draw the title plate and the controls hint at the screen edges."""
    title = font.render("Bal's Sound Garden", False, (74, 56, 44))
    pad = 3
    pw = title.get_width() + pad * 2 + 2
    ph = title.get_height() + pad * 2
    # soft drop shadow so the plate lifts off the scene a little
    sh = pygame.Surface((pw + 2, ph + 2), pygame.SRCALPHA)
    sh.fill((40, 32, 28, 70))
    surf.blit(sh, (5 + 1, 4 + 2))
    # warm cream plate with a top sheen line and a soft border
    panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
    panel.fill((250, 242, 226, 222))
    pygame.draw.line(panel, (255, 250, 238, 220), (1, 1), (pw - 2, 1))     # top sheen
    pygame.draw.rect(panel, (198, 168, 132, 235), panel.get_rect(), 1)     # border
    surf.blit(panel, (5, 4))
    surf.blit(title, (5 + pad + 1, 4 + pad))

    hint = font.render("WASD move  Shift run  Space jump  Z sleep  Esc quit",
                            False, (60, 58, 64))
    hp = pygame.Surface((hint.get_width() + 8, hint.get_height() + 5), pygame.SRCALPHA)
    hp.fill((250, 244, 232, 182))
    pygame.draw.line(hp, (255, 250, 240, 120), (0, 0), (hp.get_width() - 1, 0))  # top sheen
    surf.blit(hp, (4, config.H - hint.get_height() - 7))
    surf.blit(hint, (7, config.H - hint.get_height() - 5))
