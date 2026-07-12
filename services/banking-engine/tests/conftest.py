"""
Conftest — Banking Engine service-local tests.

The directory `services/banking-engine/` has a hyphen so Python cannot
import it as a package directly. This conftest adds the service root to
sys.path so that `hitl`, `compliance`, and `audit` sub-packages are
importable from test files in this directory.
"""

from pathlib import Path
import sys

_service_root = Path(__file__).parent.parent
if str(_service_root) not in sys.path:
    sys.path.insert(0, str(_service_root))
