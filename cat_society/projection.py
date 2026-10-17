"""World-to-screen projection shared by every renderer.

``project`` is the plain transform; ``project_cull`` is the same maths plus the
on-screen / haze-fade test the props use, returned in one shot."""

from . import config
from .config import FOCAL, MIN_D, FADE_S_HI, FADE_S_LO
from .utils import clamp


def project(wx, wz, cam):
    d = (wz - cam.z) + FOCAL
    if d <= MIN_D:
        return None
    scale = FOCAL / d
    sx = config.W * 0.5 + (wx - cam.x) * scale * config.SC
    sy = config.MEADOW_HORIZON + (config.GROUND_Y - config.MEADOW_HORIZON) * scale
    return sx, sy, scale


def project_cull(wx, wz, cam):
    # same projection + cull thresholds the props use, returned in one shot
    d = (wz - cam.z) + FOCAL
    if d <= MIN_D:
        return None
    scale = FOCAL / d
    if scale <= FADE_S_LO:
        return None
    sy = config.MEADOW_HORIZON + (config.GROUND_Y - config.MEADOW_HORIZON) * scale
    if sy < config.HORIZON - 80 or sy > config.H + 260:
        return None
    sx = config.W * 0.5 + (wx - cam.x) * scale * config.SC
    mx = int(config.W * 0.45)
    if sx < -mx or sx > config.W + mx:
        return None
    fade = (FADE_S_HI - scale) / (FADE_S_HI - FADE_S_LO) if scale < FADE_S_HI else 0.0
    return sx, sy, scale, clamp(fade, 0.0, 1.0)
