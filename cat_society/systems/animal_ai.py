"""The little brain that makes an animal wander believably.

This is deliberately tiny.  Each animal flips between a few moods, idle, walk,
sleep, play, flee and approach, on short random timers.  The cat is the spark
the world reacts to: shy animals run from it, friendly ones drift over to say
hello.

The module never imports the :class:`Animal` type, it just reads and writes
plain attributes on whatever object it is handed.  That keeps the imports
one-directional (``entities`` -> ``systems``) and avoids a loop.

``ctx`` is a small dict the spawn manager fills in each frame:

* ``cat_x`` / ``cat_z`` -- where the cat is
* ``valid(x, z, aquatic)`` -- True if that spot is good ground to stand on
* ``in_water(x, z)`` -- True if that spot is water the animal should avoid
"""

import math


# distances are in world units, matching the cat's speed scale
_FLEE_NEAR = 140.0      # shy animals bolt when the cat is this close
_FLEE_STOP = 320.0      # ...and relax again once it is this far
_CURIOUS = 300.0        # friendly animals notice the cat within this ring
_GREET = 90.0           # ...and stop to play once basically next to it
_LISTEN_RING = 130.0    # how close listeners settle when Bal performs
_LISTEN_RING_SHY = 250.0  # shy creatures keep a respectful distance

# These animals remain active after dark.  Everyone else gradually settles
# into the existing cozy sleep pose as dusk deepens.
_NOCTURNAL = {"owl", "fox", "raccoon", "tanuki", "hedgehog", "frog"}


def _pick_target(animal, ctx, reach):
    """Choose a fresh wander target near home that sits on good ground.

    Tries a handful of random spots and keeps the first valid one.  If none
    work (penned in by water, say) the animal just stays put.
    """
    rng = animal.rng
    for _ in range(6):
        ang = rng.uniform(0.0, math.tau)
        dist = rng.uniform(reach * 0.3, reach)
        tx = animal.home_x + math.cos(ang) * dist
        tz = animal.home_z + math.sin(ang) * dist
        if ctx["valid"](tx, tz, animal.spec.semi_aquatic):
            animal.tx, animal.tz = tx, tz
            return True
    animal.tx, animal.tz = animal.x, animal.z
    return False


def _steer(animal, dt, tx, tz, speed):
    """Drive velocity toward a point and report how close we now are."""
    dx = tx - animal.x
    dz = tz - animal.z
    dist = math.hypot(dx, dz)
    if dist < 1.0:
        animal.vx = 0.0
        animal.vz = 0.0
        return 0.0
    animal.vx = dx / dist * speed
    animal.vz = dz / dist * speed
    return dist


def _hop_pulse(animal):
    """Hoppers bounce on a loose rhythm while they travel."""
    if animal.spec.move == "hop" and animal.on_ground:
        if animal.rng.random() < 0.06:
            animal.hop()


def clamp01(value):
    return max(0.0, min(1.0, float(value)))


def step_ai(animal, dt, ctx):
    rng = animal.rng
    spec = animal.spec

    # Story clients use the same body and animation system as wild animals,
    # but their destination is chosen by the shop queue rather than wandering
    # AI.  The branch is deliberately generic so no story module is imported.
    script = ctx.get("script")
    if script is not None:
        mode = script.get("mode", "idle")
        animal.mood = script.get("mood", animal.mood)
        animal.dance = script.get("dance", animal.dance)
        if mode == "move":
            dist = _steer(animal, dt, script.get("x", animal.x),
                          script.get("z", animal.z),
                          script.get("speed", spec.speed))
            animal.state = "walk"
            _hop_pulse(animal)
            if dist <= script.get("stop", max(6.0, spec.radius)):
                animal.vx = animal.vz = 0.0
                animal.state = "idle"
        else:
            animal.vx *= 0.35
            animal.vz *= 0.35
            animal.state = mode if mode in ("idle", "sleep", "play", "listen") else "idle"
            if mode == "play" and spec.hop_power > 0.0 and animal.on_ground and rng.random() < 0.06:
                animal.hop()
        return

    cat_dx = ctx["cat_x"] - animal.x
    cat_dz = ctx["cat_z"] - animal.z
    cat_dist = math.hypot(cat_dx, cat_dz)

    # --- music in the air takes priority over everything ------------------
    # While Bal performs, every animal in earshot drifts over to listen.
    # Shy creatures only dare to come if the song is gentle -- and even then
    # they keep a respectful ring; that little fox creeping closer to a soft
    # lullaby is exactly the moment this game is about.
    song = ctx.get("song")
    if song is not None:
        sd = math.hypot(song["x"] - animal.x, song["z"] - animal.z)
        # every creature answers the music -- the timid ones just keep a
        # wider ring when the song is loud, watching and bobbing from afar
        wary = spec.temperament == "shy" and not song["gentle"]
        if sd < song["radius"]:
            animal.dance = song["beat"] + animal.phase
            if animal.ai_state != "listen":
                animal.ai_state = "listen"
                # every listener picks its own seat on a loose ring around Bal
                ring = (_LISTEN_RING_SHY if spec.temperament == "shy"
                        else _LISTEN_RING) * rng.uniform(0.85, 1.25)
                if wary:
                    ring *= 1.9                # loud song: admire from afar
                ang = math.atan2(animal.z - song["z"], animal.x - song["x"])
                ang += rng.uniform(-0.5, 0.5)
                animal.tx = song["x"] + math.cos(ang) * ring
                animal.tz = song["z"] + math.sin(ang) * ring
                if not ctx["valid"](animal.tx, animal.tz, spec.semi_aquatic):
                    animal.tx, animal.tz = animal.x, animal.z
            dist = math.hypot(animal.tx - animal.x, animal.tz - animal.z)
            if dist > 26.0:
                _steer(animal, dt, animal.tx, animal.tz, spec.speed * 0.7)
                animal.state = "walk"
            else:
                animal.vx *= 0.5
                animal.vz *= 0.5
                animal.state = "listen"
                animal.mood = "happy"
            return
    elif animal.ai_state == "listen":
        # the song has ended: stretch, look around, wander home
        animal.ai_state = "idle"
        animal.ai_timer = rng.uniform(1.0, 2.2)
        animal.mood = "neutral"
        animal.state = "idle"

    # --- the meadow follows the clock -------------------------------------
    night = clamp01(ctx.get("night", 0.0))
    nocturnal = getattr(animal, "key", "") in _NOCTURNAL
    if animal.ai_state == "night_sleep" and (night < .34 or nocturnal):
        animal.ai_state = "idle"
        animal.ai_timer = rng.uniform(.7, 2.0)
        animal.state = "idle"

    if not nocturnal and night > .34:
        # Individuals settle at slightly different points during dusk, but by
        # full night all daytime animals are lying down with closed eyes.
        personal = .34 + .42 * ((math.sin(animal.phase * 1.71) + 1.0) * .5)
        if night >= personal:
            animal.ai_state = "night_sleep"
            animal.ai_timer = 9999.0
            animal.vx = 0.0
            animal.vz = 0.0
            animal.state = "sleep"
            animal.mood = "neutral"
            return

    # --- reactions to the cat take priority over plain wandering ----------
    if spec.temperament == "shy" and cat_dist < _FLEE_NEAR:
        animal.ai_state = "flee"
        animal.ai_timer = max(animal.ai_timer, 0.4)
    elif spec.temperament == "friendly" and animal.ai_state not in ("approach", "play"):
        if _GREET < cat_dist < _CURIOUS and rng.random() < 0.4 * dt + 0.004:
            animal.ai_state = "approach"
            animal.ai_timer = 4.0

    animal.ai_timer -= dt

    # ---------------------------------------------------------------- flee
    if animal.ai_state == "flee":
        # run directly away from the cat, fast, in short panicked hops
        if cat_dist > 1.0:
            away_x = animal.x - cat_dx / cat_dist * 60.0
            away_z = animal.z - cat_dz / cat_dist * 60.0
        else:
            away_x, away_z = animal.x + 40.0, animal.z
        if not ctx["valid"](away_x, away_z, spec.semi_aquatic):
            away_x, away_z = animal.home_x, animal.home_z
        _steer(animal, dt, away_x, away_z, spec.speed * 1.5)
        animal.state = "walk"
        if spec.move == "hop" and animal.on_ground and rng.random() < 0.18:
            animal.hop()
        if cat_dist > _FLEE_STOP or animal.ai_timer <= 0.0:
            animal.ai_state = "idle"
            animal.ai_timer = rng.uniform(0.6, 1.6)
        return

    # ------------------------------------------------------------- approach
    if animal.ai_state == "approach":
        dist = _steer(animal, dt, ctx["cat_x"], ctx["cat_z"], spec.speed * 0.8)
        animal.state = "walk"
        animal.mood = "happy"
        _hop_pulse(animal)
        if dist <= _GREET or animal.ai_timer <= 0.0:
            animal.ai_state = "play"
            animal.ai_timer = rng.uniform(1.2, 2.4)
        return

    # ----------------------------------------------------------------- play
    if animal.ai_state == "play":
        animal.vx *= 0.6
        animal.vz *= 0.6
        animal.state = "play"
        animal.mood = "happy"
        if spec.hop_power > 0.0 and animal.on_ground and rng.random() < 0.05:
            animal.hop()
        if animal.ai_timer <= 0.0:
            animal.ai_state = "idle"
            animal.ai_timer = rng.uniform(1.0, 2.5)
            animal.mood = "neutral"
        return

    # ---------------------------------------------------------------- sleep
    if animal.ai_state == "sleep":
        animal.vx = 0.0
        animal.vz = 0.0
        animal.state = "sleep"
        if animal.ai_timer <= 0.0:
            animal.ai_state = "idle"
            animal.ai_timer = rng.uniform(1.0, 2.5)
        return

    # ----------------------------------------------------------------- walk
    if animal.ai_state == "walk":
        # if we have wandered into water we should not be in, head home
        if not spec.semi_aquatic and ctx["in_water"](animal.x, animal.z):
            animal.tx, animal.tz = animal.home_x, animal.home_z
        dist = _steer(animal, dt, animal.tx, animal.tz, spec.speed)
        animal.state = "walk"
        _hop_pulse(animal)
        if dist <= max(6.0, spec.radius) or animal.ai_timer <= 0.0:
            animal.ai_state = "idle"
            animal.ai_timer = rng.uniform(0.8, 2.6)
        return

    # ----------------------------------------------------------------- idle
    # standing around: stop, then roll for what to do next
    animal.vx *= 0.4
    animal.vz *= 0.4
    animal.state = "idle"
    if animal.ai_timer <= 0.0:
        roll = rng.random()
        if roll < 0.06 and spec.move != "hop" and not (nocturnal and night > .45):
            animal.ai_state = "sleep"
            animal.ai_timer = rng.uniform(4.0, 9.0)
        elif roll < 0.16 and spec.hop_power > 0.0:
            animal.ai_state = "play"
            animal.ai_timer = rng.uniform(0.8, 1.6)
        else:
            _pick_target(animal, ctx, animal.roam)
            animal.ai_state = "walk"
            animal.ai_timer = rng.uniform(1.5, 4.0)
