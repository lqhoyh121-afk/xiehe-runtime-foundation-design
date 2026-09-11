"""Explicit TEST ONLY host CLI. Laiqh."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_author.cli import main

if __name__ == '__main__':
    sys.exit(main(synthetic=True))
