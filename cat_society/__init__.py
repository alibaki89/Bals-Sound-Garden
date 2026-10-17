"""Cat Society - a cozy pixel-art top-down cat sim.

The package is split so each system is easy to find:

* :mod:`cat_society.config` / :mod:`cat_society.palette` - tunables and colours
* :mod:`cat_society.utils` - small math/seed helpers
* :mod:`cat_society.camera` / :mod:`cat_society.projection` - the follow camera
  and the world-to-screen transform
* :mod:`cat_society.world` - generation + the water biome
* :mod:`cat_society.entities` - the cat, critters and petals
* :mod:`cat_society.render` - every drawing routine, grouped by what it paints
* :mod:`cat_society.game` - the :class:`~cat_society.game.Game` loop that ties it
  all together
"""

__version__ = "1.0.0"
