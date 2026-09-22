"""Vercel entry point.

Vercel turns each file under `api/` into a serverless function and looks for a
WSGI callable named `app`. It finds it by parsing this file and reading the
module body, so the assignment has to be a plain top-level statement. An
assignment nested inside a `try` block is invisible to that scan and the build
fails with "Could not find a top-level app" before anything ever runs, which is
why the work below is done in a function and assigned once at the end.

Everything else, including the URL routing, is the ordinary Django application.

The project root is put on the import path because this module is imported from
inside `api/`, so `FitnessEmpire` and `FitnessGYM` are not importable without
it.
"""

import html
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FitnessEmpire.settings")


def configuration_required(message):
    """A stand-in app for when required settings are missing.

    Without this, a missing environment variable kills the Python process
    before it can answer anything, so every request is an opaque 500 and the
    real reason is only visible to whoever can read the platform logs. This
    keeps the refusal to run, but says why on the page.

    503 rather than 500: the deployment is not broken, it is not configured,
    and the difference tells a monitor not to treat it as a crash loop.
    """

    def serve(environ, start_response):
        body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Configuration required</title>
<style>
  body {{ margin:0; min-height:100vh; display:grid; place-items:center;
         padding:2rem; background:#0a0c0f; color:#e9ecf1;
         font:16px/1.6 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
  main {{ max-width:44rem; }}
  h1 {{ margin:0 0 .5rem; font-size:1.5rem; color:#fff; }}
  p {{ color:#a7b0bd; }}
  pre {{ white-space:pre-wrap; word-break:break-word; margin:1.5rem 0;
         padding:1.25rem; border-radius:12px; background:#12151b;
         border:1px solid rgba(255,255,255,.12); color:#e9ecf1;
         font:14px/1.7 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  code {{ background:rgba(255,255,255,.08); padding:.1em .4em; border-radius:4px; }}
</style>
</head>
<body>
<main>
  <h1>Fitness Empire is not configured yet</h1>
  <p>The site is deployed, but it will not start until these are set.</p>
  <pre>{html.escape(message)}</pre>
  <p>Nothing is wrong with the build. Set the variables, redeploy, and this
     page goes away. See <code>DEPLOY.md</code> in the repository.</p>
</main>
</body>
</html>"""
        payload = body.encode("utf-8")
        start_response(
            "503 Service Unavailable",
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(payload))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [payload]

    return serve


def build_application():
    """The Django app, or the page explaining why it will not start."""
    try:
        from FitnessEmpire.wsgi import application

        return application
    except Exception as exc:  # noqa: BLE001
        from django.core.exceptions import ImproperlyConfigured

        # Only a missing-configuration error is turned into a page. Anything
        # else is a genuine fault and should keep crashing loudly, with its
        # traceback in the platform log where it belongs.
        if not isinstance(exc, ImproperlyConfigured):
            raise

        print(f"Refusing to start: {exc}", file=sys.stderr)
        return configuration_required(str(exc))


# Top-level and unconditional, so Vercel's entrypoint scan can see it.
app = build_application()
application = app
