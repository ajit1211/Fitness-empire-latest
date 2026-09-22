"""PythonAnywhere overrides.

`settings.py` now reads everything from the environment, so it is the only
settings module the project needs, including on Vercel. This file stays for the
PythonAnywhere deployment, which has a MySQL instance rather than a Postgres
connection string.

Point DJANGO_SETTINGS_MODULE at this module only on that host. It imports the
real settings and swaps in MySQL.

The database password and the Gmail app password that used to sit in this file
in plain text are gone. Both were committed and are in the public git history,
so treat them as leaked: rotate the MySQL password and revoke the Gmail app
password, then set these variables in the host's environment instead.
"""

import os

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ["MYSQL_NAME"],
        "USER": os.environ["MYSQL_USER"],
        "PASSWORD": os.environ["MYSQL_PASSWORD"],
        "HOST": os.environ["MYSQL_HOST"],
        "PORT": int(os.environ.get("MYSQL_PORT", 3306)),
        "CONN_MAX_AGE": 60,
    }
}
