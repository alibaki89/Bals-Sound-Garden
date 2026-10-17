"""Audio subsystem: programmatic synthesis, the playback engine, project
rendering / WAV export and user-sample import.

Nothing here imports pygame at module import time except :mod:`engine`, so the
synth + export can be unit-tested and run head-less.
"""

SR = 44100
