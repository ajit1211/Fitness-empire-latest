"""Guards on the deployment entry point.

These do not exercise Django. They check the shape of `api/index.py`, because
Vercel reads that file statically at build time and two separate deploys were
lost to problems a normal test run could not see.
"""

import ast
import pathlib

from django.test import SimpleTestCase

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "api" / "index.py"


def top_level_names(source):
    """The names Vercel's entrypoint scan can see.

    It parses the module and looks at the module body only. A name bound inside
    a `try` block is module-level to Python but invisible here, which is what
    broke the build: the assignment sat inside a try/except and Vercel reported
    "Could not find a top-level app".
    """
    names = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            names += [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


class VercelEntrypointTests(SimpleTestCase):
    def test_the_entrypoint_file_exists(self):
        self.assertTrue(ENTRYPOINT.is_file(), f"{ENTRYPOINT} is missing")

    def test_the_entrypoint_is_valid_python(self):
        ast.parse(ENTRYPOINT.read_text(encoding="utf-8"))

    def test_a_callable_is_bound_where_the_build_scan_looks(self):
        names = top_level_names(ENTRYPOINT.read_text(encoding="utf-8"))
        self.assertTrue(
            {"app", "application", "handler"} & set(names),
            "Vercel needs a top-level app, application or handler in "
            "api/index.py. Assignments nested inside try/if blocks do not "
            f"count. Found: {names}",
        )

    def test_the_project_root_is_added_to_the_import_path(self):
        # Without this the function cannot import FitnessEmpire or FitnessGYM,
        # because it is imported from inside api/.
        source = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("sys.path.insert", source)

    def test_the_settings_module_is_named(self):
        source = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("DJANGO_SETTINGS_MODULE", source)


class VercelConfigTests(SimpleTestCase):
    def test_vercel_json_is_valid_and_points_at_the_entrypoint(self):
        import json

        config = json.loads((REPO_ROOT / "vercel.json").read_text(encoding="utf-8"))

        sources = [build["src"] for build in config.get("builds", [])]
        self.assertIn("api/index.py", sources)

        destinations = [route.get("dest") for route in config.get("routes", [])]
        self.assertIn("api/index.py", destinations)

    def test_requirements_exclude_the_package_that_cannot_build(self):
        # mysqlclient is a C extension needing MySQL headers the Vercel image
        # does not have, so its presence fails the install outright.
        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        for line in requirements.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            self.assertNotIn("mysqlclient", line)

    def test_requirements_include_what_production_imports(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        for package in ("whitenoise", "dj-database-url", "psycopg"):
            self.assertIn(package, requirements)


class SettingsSafetyTests(SimpleTestCase):
    def test_no_credentials_are_hardcoded_in_the_settings_modules(self):
        leaked = ("ajit@9819978432", "ugkn dzye yjez kimx", "django-insecure-prune4")
        for name in ("settings.py", "production_setting.py"):
            source = (REPO_ROOT / "FitnessEmpire" / name).read_text(encoding="utf-8")
            for secret in leaked:
                self.assertNotIn(
                    secret,
                    source,
                    f"{name} still contains a credential that belongs in the "
                    "environment",
                )
