"""Geometry and interaction checks for the reorganized Music Maker UI."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

passed = failed = 0


def check(label, condition):
    global passed, failed
    ok = bool(condition)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


class Engine:
    def is_playing(self): return False
    def stop_music(self): pass
    def play_project(self, project, samples=None, loop=False): pass
    def preview_component(self, comp, bpm=100): pass
    def invalidate(self): pass
    def playhead_fraction(self): return 0.0


class Collection:
    def owned_on_track(self, track):
        from cat_society.components import catalog
        return [c for c in catalog.ALL if c.get("starter") and c.get("track") == track]
    def owned_effects(self): return []
    def discovery_order(self, cid): return 0


class Projects:
    def list_projects(self): return []
    def save(self, project): return project


class App:
    def __init__(self, size):
        self.window = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.engine = Engine()
        self.collection = Collection()
        self.projects = Projects()
        self.pending_project = None
        self.goto_calls = []
    def goto(self, name): self.goto_calls.append(name)
    def refresh_projects(self): return []


def click(screen, pos):
    screen.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    screen.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def no_pair_overlap(rects):
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if a.colliderect(b):
                return False
    return True


pygame.init()
from cat_society.screens.maker import MakerScreen

for size in ((1024, 640), (1280, 720), (1600, 900)):
    app = App(size)
    maker = MakerScreen(app)
    maker.on_enter()
    maker.draw(app.window)
    label = "%dx%d" % size

    top_groups = [maker._top_groups[k] for k in
                  ("song", "playback", "project", "tempo", "bars", "tools")]
    check(label + " top groups stay inside header",
          all(maker.topbar.contains(r) for r in top_groups))
    check(label + " top groups do not overlap", no_pair_overlap(top_groups))
    check(label + " transport buttons stay inside the header",
          all(maker.topbar.contains(b.rect) for b in maker.transport))
    check(label + " edit segments fit their group",
          maker._top_groups["tools"].contains(maker._tiles_rect)
          and maker._top_groups["tools"].contains(maker._connect_rect)
          and not maker._tiles_rect.colliderect(maker._connect_rect))
    check(label + " workspace sections stay ordered",
          maker.topbar.bottom <= maker.timeline_header.top
          and maker.timeline_header.bottom == maker.ruler.top
          and maker.ruler.bottom == maker.grid.top
          and maker.grid.bottom < maker.browser.top)
    check(label + " drawer controls remain inside drawer",
          maker.browser.contains(maker._sort_rect)
          and maker.browser.contains(maker._search_rect)
          and maker.browser.contains(maker._browser_area))
    check(label + " visible sound chips remain inside their content area",
          all(maker._browser_area.contains(rect) for rect, _ in maker._chip_rects))

    click(maker, maker._connect_rect.center)
    check(label + " Connect segment enters existing workflow", maker.connect_mode)
    maker.draw(app.window)
    check(label + " Connect guidance remains in arrangement header",
          all(maker.timeline_header.contains(rect) for rect, _ in maker._pill_rects))
    click(maker, maker._tiles_rect.center)
    check(label + " Tiles segment returns to ordinary editing", not maker.connect_mode)

print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
