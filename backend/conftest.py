import sys
from pathlib import Path

# Lets `python -m pytest backend` (from the repo root) find simulation.py etc.
sys.path.insert(0, str(Path(__file__).parent))
