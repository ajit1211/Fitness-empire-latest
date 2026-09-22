"""Vercel entry point.

Vercel turns each file under `api/` into a serverless function and looks for a
module-level WSGI callable named `app`. Everything else, including the URL
routing, is the ordinary Django application.

The project root is put on the import path because the function is imported
from inside `api/`, so `FitnessEmpire` and `FitnessGYM` are not importable
without it.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FitnessEmpire.settings")

from FitnessEmpire.wsgi import application  # noqa: E402

app = application
