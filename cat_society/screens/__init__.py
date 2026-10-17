"""Top-level screens (menu, explore, music maker, your music) driven by the App.

Each screen exposes ``handle_event(event)``, ``update(dt)`` and ``draw(surface)``
and uses ``self.app`` for shared state (window, audio engine, collection,
samples) and to switch screens via ``self.app.goto(name)``.
"""
