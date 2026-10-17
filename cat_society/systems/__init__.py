"""Cross-cutting systems that act on the running game.

These take the live :class:`~cat_society.game.Game` instance and read/modify
its state, rather than owning state themselves.  Keeping them out of
:mod:`cat_society.game` keeps the loop short and the input/interaction rules
easy to find.
"""
