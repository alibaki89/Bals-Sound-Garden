"""The follow camera (world origin tracking the cat)."""

from . import config


class Camera:
    def __init__(self):
        self.x = 0.0
        self.z = 0.0

    def snap(self, x, z):
        self.x = x
        self.z = z

    def follow(self, x, z):
        # Lock onto the cat, but quantise the HORIZONTAL position to the low-res
        # canvas pixel grid.  This is the main motion-comfort fix.  Without it,
        # sub-pixel camera motion makes every distant prop cross its own integer
        # rounding boundary at a slightly different instant, so the far field
        # appears to shimmer / crawl as you strafe.  Snapping the world origin
        # to whole canvas pixels makes the entire scene step in lockstep -- one
        # clean pixel at a time, which reads as deliberate and stable instead of
        # scratchy.  Depth (z) stays continuous so forward/back motion and the
        # cat's own scale stay perfectly smooth.
        self.x = round(x * config.SC) / config.SC if config.SC > 0 else x
        self.z = z
