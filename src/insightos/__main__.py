"""Allow ``python -m insightos``."""

import sys

from insightos.cli import main

if __name__ == "__main__":
    sys.exit(main())
