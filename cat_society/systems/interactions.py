"""The cat's two contextual actions: getting in/out of a boat and using a well
or fountain.

Where the boats and interactive props actually live is decided in
:mod:`cat_society.world.water`; these functions just wire the cat's request up
to it.  (Ordinary solid-prop collision is handled inside
:class:`cat_society.entities.cat.Cat` and
:class:`cat_society.world.generation.World`, not here.)"""

from ..config import BOAT_REACH, USE_REACH


def board_or_exit(game):
    if game.cat.boat is not None:
        # step out onto the nearest dry land
        sx, sz = game.water.nearest_shore(game.cat.x, game.cat.z)
        game.cat.boat.occupied = False
        game.cat.boat = None
        game.cat.x, game.cat.z = sx, sz
        game.cat.swim = 0.0
        game.cat.in_water = False
        return

    # re-board a boat that's already floating nearby
    bo = game.water.nearest_boat(game.cat.x, game.cat.z, BOAT_REACH)
    if bo is None:
        # otherwise drop a fresh test boat on the closest reachable water
        spot = game.water.nearest_water(game.cat.x, game.cat.z, want=0.28)
        if spot is None:
            game.cat.set_expression("sad")   # no water within reach
            return
        bo = game.water.spawn_boat(spot[0], spot[1])
        bo.facing = game.cat.facing
    bo.occupied = True
    game.cat.boat = bo
    game.cat.x, game.cat.z = bo.x, bo.z
    game.cat.facing = bo.facing
    game.cat.swim = 0.0
    game.cat.in_water = False


def interact(game):
    ob = game.water.nearest_interactive(game.cat.x, game.cat.z, USE_REACH)
    if ob is not None:
        ob.spark = 1.2
        game.cat.set_expression("happy")
        game.cat.sleeping = False
