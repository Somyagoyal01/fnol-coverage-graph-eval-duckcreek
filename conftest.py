"""Makes the repo root importable when running plain `pytest` from a fresh clone."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
