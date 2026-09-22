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


class DemoModeTests(SimpleTestCase):
    """A deployment with nothing configured must run, and must say so."""

    def settings_with(self, **environ):
        """Load the settings module fresh under a given environment."""
        import importlib
        import os
        from unittest import mock

        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("DJANGO_", "DATABASE_", "VERCEL", "ALLOW_"))}
        base.update(environ)

        with mock.patch.dict(os.environ, base, clear=True):
            module = importlib.import_module("FitnessEmpire.settings")
            return importlib.reload(module)

    def tearDown(self):
        # Leave the module matching the environment the rest of the suite runs
        # under, or later imports of it see the last test's values.
        import importlib

        importlib.reload(importlib.import_module("FitnessEmpire.settings"))

    def test_a_deployment_with_no_configuration_still_boots(self):
        conf = self.settings_with(VERCEL="1")
        self.assertFalse(conf.DEBUG)
        self.assertTrue(conf.SECRET_KEY)
        self.assertTrue(conf.DATABASES["default"]["NAME"])

    def test_both_shortcomings_are_reported(self):
        conf = self.settings_with(VERCEL="1")
        self.assertTrue(conf.DEMO_MODE)
        self.assertEqual(len(conf.DEMO_REASONS), 2)
        joined = " ".join(conf.DEMO_REASONS)
        self.assertIn("DJANGO_SECRET_KEY", joined)
        self.assertIn("DATABASE_URL", joined)

    def test_a_generated_key_is_actually_random(self):
        first = self.settings_with(VERCEL="1").SECRET_KEY
        second = self.settings_with(VERCEL="1").SECRET_KEY
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 50)

    def test_setting_the_key_removes_only_that_warning(self):
        conf = self.settings_with(VERCEL="1", DJANGO_SECRET_KEY="x" * 60)
        self.assertTrue(conf.DEMO_MODE)
        self.assertEqual(len(conf.DEMO_REASONS), 1)
        self.assertIn("DATABASE_URL", conf.DEMO_REASONS[0])

    def test_a_fully_configured_deployment_shows_no_banner(self):
        conf = self.settings_with(
            VERCEL="1",
            DJANGO_SECRET_KEY="x" * 60,
            DATABASE_URL="postgresql://u:p@host/db?sslmode=require",
        )
        self.assertFalse(conf.DEMO_MODE)
        self.assertEqual(conf.DEMO_REASONS, [])
        self.assertEqual(
            conf.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql"
        )

    def test_local_development_is_never_in_demo_mode(self):
        conf = self.settings_with()
        self.assertTrue(conf.DEBUG)
        self.assertFalse(conf.DEMO_MODE)

    def test_the_banner_is_wired_into_every_page(self):
        import pathlib

        base_template = (REPO_ROOT / "templates" / "base.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("demo_mode", base_template)
        self.assertIn("demo-bar", base_template)

        settings_source = (
            REPO_ROOT / "FitnessEmpire" / "settings.py"
        ).read_text(encoding="utf-8")
        self.assertIn("context_processors.demo_notice", settings_source)
        del pathlib


class BlankEnvironmentVariableTests(SimpleTestCase):
    """A dashboard entry left empty must behave as if it were never created.

    Hosting dashboards store a variable with an empty value box as "", not as
    absent, so `os.environ.get(name, default)` returns the empty string and the
    default is silently lost. A blank DJANGO_HSTS_SECONDS reached `int("")` and
    took the deployed site down with a 500 on every request.
    """

    BLANK = {
        "DJANGO_SECRET_KEY": "",
        "DATABASE_URL": "",
        "DJANGO_HSTS_SECONDS": "",
        "DJANGO_DEBUG": "",
        "DJANGO_ALLOWED_HOSTS": "",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "",
        "DJANGO_LOG_LEVEL": "",
        "EMAIL_HOST": "",
        "EMAIL_PORT": "",
        "EMAIL_HOST_USER": "",
        "EMAIL_HOST_PASSWORD": "",
        "DEFAULT_FROM_EMAIL": "",
        "EMAIL_BACKEND": "",
        "PAYPAL_RECEIVER_EMAIL": "",
        "PAYPAL_TEST": "",
        "INR_TO_USD_RATE": "",
        "SERVE_MEDIA_FILES": "",
    }

    def load(self, **overrides):
        import importlib
        import os
        from unittest import mock

        environ = dict(self.BLANK)
        environ["VERCEL"] = "1"
        environ.update(overrides)

        with mock.patch.dict(os.environ, environ, clear=True):
            return importlib.reload(importlib.import_module("FitnessEmpire.settings"))

    def tearDown(self):
        import importlib

        importlib.reload(importlib.import_module("FitnessEmpire.settings"))

    def test_the_settings_module_loads_with_every_variable_blank(self):
        conf = self.load()
        self.assertFalse(conf.DEBUG)
        self.assertTrue(conf.DEMO_MODE)

    def test_blank_numbers_fall_back_instead_of_raising(self):
        conf = self.load()
        self.assertEqual(conf.SECURE_HSTS_SECONDS, 0)
        self.assertEqual(conf.EMAIL_PORT, 587)

    def test_blank_strings_fall_back_to_their_defaults(self):
        conf = self.load()
        self.assertEqual(conf.EMAIL_HOST, "smtp.gmail.com")
        self.assertEqual(conf.INR_TO_USD_RATE, "0.012")
        self.assertEqual(conf.LOGGING["root"]["level"], "INFO")
        self.assertTrue(conf.PAYPAL_RECEIVER_EMAIL)

    def test_a_blank_flag_keeps_its_default_rather_than_turning_off(self):
        # SERVE_MEDIA_FILES defaults to on. A blank box must not switch it off,
        # which would break every product image.
        conf = self.load()
        self.assertTrue(conf.SERVE_MEDIA_FILES)
        self.assertTrue(conf.PAYPAL_TEST)

    def test_whitespace_counts_as_blank(self):
        conf = self.load(DJANGO_HSTS_SECONDS="   ", EMAIL_PORT="\t")
        self.assertEqual(conf.SECURE_HSTS_SECONDS, 0)
        self.assertEqual(conf.EMAIL_PORT, 587)

    def test_values_are_stripped_of_stray_whitespace(self):
        # Pasting into a dashboard field often carries a trailing space.
        conf = self.load(DJANGO_HSTS_SECONDS=" 3600 ", EMAIL_HOST=" smtp.example.com ")
        self.assertEqual(conf.SECURE_HSTS_SECONDS, 3600)
        self.assertEqual(conf.EMAIL_HOST, "smtp.example.com")

    def test_a_real_value_is_still_honoured(self):
        conf = self.load(DJANGO_HSTS_SECONDS="31536000", EMAIL_PORT="2525")
        self.assertEqual(conf.SECURE_HSTS_SECONDS, 31536000)
        self.assertEqual(conf.EMAIL_PORT, 2525)

    def test_a_non_numeric_value_is_reported_rather_than_ignored(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured) as caught:
            self.load(DJANGO_HSTS_SECONDS="thirty days")
        self.assertIn("DJANGO_HSTS_SECONDS", str(caught.exception))
        self.assertIn("whole number", str(caught.exception))

    def test_a_bad_exchange_rate_fails_the_deploy_not_the_checkout(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            self.load(INR_TO_USD_RATE="abc")
        with self.assertRaises(ImproperlyConfigured):
            self.load(INR_TO_USD_RATE="-1")

    def test_no_setting_reads_the_environment_without_the_helpers(self):
        # Every read has to go through env/env_int/env_flag/env_list, or the
        # blank-value bug comes straight back the next time one is added.
        source = (REPO_ROOT / "FitnessEmpire" / "settings.py").read_text(
            encoding="utf-8"
        )
        body = source.split("def env_list", 1)[1]
        offenders = [
            line.strip()
            for line in body.splitlines()
            if "os.environ" in line and not line.strip().startswith("#")
        ]
        self.assertEqual(offenders, [], f"read the environment directly: {offenders}")
