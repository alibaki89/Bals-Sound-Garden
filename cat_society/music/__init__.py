"""Music projects: the data model the Music Maker edits, plus save/load.

A :class:`~cat_society.music.project.Project` is a tempo + a set of tracks, and
each track holds clips (a component placed at a grid step).  The audio for a
project is produced by :mod:`cat_society.audio.export`, so playback in the
maker and the exported WAV always match.
"""
