"""Ascend assets, works from source and a frozen app."""
from pathlib import Path
import sys

def asset(name):
    return str(Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / name)
