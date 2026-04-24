"""Put `noirdoc/hooks/` on sys.path so editors/type-checkers resolve `import guard`.

pytest already adds it via pyproject's `pythonpath`, but tools like
Pyright read sys.path not pytest config.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).parent.parent / "noirdoc" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
