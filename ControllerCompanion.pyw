"""Double-click launcher (no console window). Also the PyInstaller entry point."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from controller_companion.app import main

raise SystemExit(main())
