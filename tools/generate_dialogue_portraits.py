#!/usr/bin/env python3
"""Rebuild dialogue portraits from actual in-game Explore screenshots.

The tool renders each existing entity alone at the same normal projection scale
as Bal, captures the real low-resolution game canvas, removes the unchanged
world background, and crops the head. No external or replacement animal art is
used.
"""

from __future__ import annotations

import os
import random
import shutil
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("BAL_SOUND_GARDEN_DATA_DIR", tempfile.mkdtemp(prefix="bsg-portraits-"))
os.environ.setdefault("BAL_SOUND_GARDEN_EXPORTS_DIR", tempfile.mkdtemp(prefix="bsg-exports-"))

import numpy as np
import pygame
from PIL import Image, ImageDraw

from cat_society.app import App
from cat_society.entities.animals import Animal, SPECIES_KEYS
from cat_society.projection import project

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cat_society" / "assets" / "dialogue_photos"
CONTACT = ROOT / "DIALOGUE_PORTRAITS_CONTACT_SHEET.png"

# Head centers measured within each complete in-game entity bounding box.
HEAD = {
    "bal": (0.54, 0.28, 0.56),
    "dog": (0.78, 0.34, 0.48),
    "rabbit": (0.50, 0.34, 0.88),
    "deer": (0.82, 0.30, 0.62),
    "sheep": (0.80, 0.38, 0.54),
    "cow": (0.80, 0.38, 0.52),
    "frog": (0.50, 0.40, 0.92),
    "bird": (0.53, 0.34, 0.80),
    "fox": (0.81, 0.32, 0.48),
    "raccoon": (0.80, 0.32, 0.54),
    "squirrel": (0.62, 0.30, 0.56),
    "turtle": (0.88, 0.42, 0.42),
    "pig": (0.80, 0.38, 0.52),
    "goat": (0.82, 0.32, 0.58),
    "chicken": (0.58, 0.32, 0.78),
    "duck": (0.70, 0.32, 0.68),
    "horse": (0.84, 0.29, 0.58),
    "owl": (0.52, 0.35, 0.82),
    "hedgehog": (0.84, 0.42, 0.48),
    "tanuki": (0.80, 0.32, 0.54),
    "butterfly": (0.50, 0.38, 1.00),
}

def _surface_rgba(surface):
    rgb = pygame.surfarray.array3d(surface).swapaxes(0, 1)
    alpha = np.full(rgb.shape[:2] + (1,), 255, dtype=np.uint8)
    return np.concatenate((rgb, alpha), axis=2)


def main():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    app = App()
    screen = app.screens["explore"]
    screen.ensure_game()
    game = screen.game
    game.time = 0.0
    try:
        game.butterflies = []
    except Exception:
        pass

    camera_x, camera_z = 400.0, 860.0
    subject_x, subject_z = camera_x, camera_z + 58.0

    def clear_scene():
        game.dbg_clear_animals(reach=9999.0)
        game.set_clear_zones([])
        game.cat.x = 5000.0
        game.cat.z = 5000.0
        game.cam.x = camera_x
        game.cam.z = camera_z

    clear_scene()
    game.paint_world()
    blank = _surface_rgba(game.canvas)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    names = ["bal"] + list(SPECIES_KEYS)
    results = []
    for species in names:
        clear_scene()
        if species == "bal":
            game.cat.x, game.cat.z = subject_x, subject_z
            game.cat.facing = 1
        else:
            animal = Animal(species, subject_x, subject_z, random.Random(712367))
            animal.facing = 1
            animal.t = 0.35
            animal.state = "idle"
            animal.mood = "neutral"
            cell = (int(animal.x // 780), int(animal.z // 780))
            game.animals.cells = {cell: [animal]}
        game.paint_world()
        frame = _surface_rgba(game.canvas)
        distance = np.abs(frame[:, :, :3].astype(np.int16)
                          - blank[:, :, :3].astype(np.int16)).sum(axis=2)
        raw_mask = distance > 18
        expected = project(subject_x, subject_z, game.cam)
        if expected is not None:
            _sx, ground_y, _scale = expected
            yy = np.arange(raw_mask.shape[0])[:, None]
            raw_mask &= yy >= int(ground_y - 60)

        # Keep the largest connected changed region. This removes unrelated
        # animated pickups or tiny scenery differences while retaining the
        # complete animal captured from the real game frame.
        height, width = raw_mask.shape
        seen = np.zeros_like(raw_mask, dtype=bool)
        largest = []
        for start_y, start_x in zip(*np.where(raw_mask)):
            if seen[start_y, start_x]:
                continue
            stack = [(int(start_y), int(start_x))]
            seen[start_y, start_x] = True
            component = []
            while stack:
                point_y, point_x = stack.pop()
                component.append((point_y, point_x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        next_y, next_x = point_y + dy, point_x + dx
                        if (0 <= next_y < height and 0 <= next_x < width
                                and raw_mask[next_y, next_x]
                                and not seen[next_y, next_x]):
                            seen[next_y, next_x] = True
                            stack.append((next_y, next_x))
            if len(component) > len(largest):
                largest = component
        mask = np.zeros_like(raw_mask, dtype=bool)
        for point_y, point_x in largest:
            mask[point_y, point_x] = True
        ys, xs = np.where(mask)
        if not len(xs):
            raise RuntimeError("No rendered pixels found for %s" % species)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        width, height = x1 - x0, y1 - y0
        ax, ay, scale = HEAD[species]
        center_x = x0 + width * ax
        center_y = y0 + height * ay
        side = max(8, int(round(max(width, height) * scale)))
        left = int(round(center_x - side / 2))
        top = int(round(center_y - side / 2))
        left = max(0, min(frame.shape[1] - side, left))
        top = max(0, min(frame.shape[0] - side, top))

        rgba = np.zeros((side, side, 4), dtype=np.uint8)
        source = frame[top:top + side, left:left + side]
        source_mask = mask[top:top + side, left:left + side]
        rgba[source_mask, :3] = source[source_mask, :3]
        rgba[source_mask, 3] = 255
        crop = Image.fromarray(rgba, "RGBA")
        # Nearest-neighbour scaling preserves the exact in-game pixels.
        fitted = crop.resize((96, 96), Image.Resampling.NEAREST)
        canvas = Image.new("RGBA", (112, 112), (0, 0, 0, 0))
        canvas.alpha_composite(fitted, (8, 8))
        output = OUT / (species + ".png")
        canvas.save(output)
        results.append((species, canvas))

    cols = 5
    rows = (len(results) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * 140, rows * 146), (244, 239, 228, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (species, image) in enumerate(results):
        x = (index % cols) * 140 + 14
        y = (index // cols) * 146 + 8
        checker = Image.new("RGBA", (112, 112), (230, 226, 217, 255))
        cdraw = ImageDraw.Draw(checker)
        for yy in range(0, 112, 8):
            for xx in range(0, 112, 8):
                if (xx // 8 + yy // 8) % 2:
                    cdraw.rectangle((xx, yy, xx + 7, yy + 7), fill=(246, 243, 236, 255))
        checker.alpha_composite(image)
        sheet.alpha_composite(checker, (x, y))
        draw.text((x, y + 116), species, fill=(45, 42, 38, 255))
    sheet.save(CONTACT)
    app._shutdown()
    pygame.quit()
    print("Wrote %d portraits and %s" % (len(results), CONTACT.name))


if __name__ == "__main__":
    main()
