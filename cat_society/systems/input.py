"""Keyboard input: per-frame discrete key handling (jump, paw, sleep, moods,
build/remove a signpost, board a boat, use a well/fountain, quit).

Continuous movement (WASD / arrows) and the run modifier (Shift) are polled
directly in :meth:`cat_society.game.Game.update`, where they feed the cat's
motion each frame; this module covers the one-shot key presses."""

import pygame

from .interactions import board_or_exit, interact


def handle_input(game):
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            game.running = False
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                game.running = False
            elif e.key == pygame.K_e:
                game.world.place("post", game.cat.x + game.cat.facing * 34, game.cat.z)
            elif e.key == pygame.K_x:
                game.world.remove_near(game.cat.x, game.cat.z)
            elif e.key == pygame.K_SPACE:
                game.cat.jump()
            elif e.key == pygame.K_z:
                if game.cat.on_ground:
                    game.cat.sleeping = not game.cat.sleeping
            elif e.key in (pygame.K_f, pygame.K_j):
                game.cat.attack()
            elif e.key == pygame.K_b:
                board_or_exit(game)
            elif e.key == pygame.K_g:
                interact(game)
            elif e.key == pygame.K_1:
                game.cat.set_expression("happy")
            elif e.key == pygame.K_2:
                game.cat.set_expression("sad")
            elif e.key == pygame.K_3:
                game.cat.set_expression("angry")
            elif e.key == pygame.K_4:
                game.cat.set_expression("neutral")
            # --- animal debug keys ---
            elif e.key == pygame.K_p:
                game.dbg_spawn_animal()
            elif e.key == pygame.K_o:
                game.dbg_cycle_species()
            elif e.key == pygame.K_k:
                game.animal_debug = not game.animal_debug
            elif e.key == pygame.K_l:
                game.dbg_clear_animals()
