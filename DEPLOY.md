# Deploying Fitness Empire to Vercel

Written for: whoever is doing the deploy, assumed comfortable with Django but
not with this project's history.

Everything in the repository is ready. What is left needs your Vercel and
GitHub accounts, so it cannot be done for you. Work through the sections in
order; the first one is not optional.

---

## 1. Rotate the leaked credentials first

Three secrets were committed to this repository and are in its git history on
GitHub. Anyone who has ever had access to the repo has them. Changing the code
does not un-publish them.

| Secret | Where it was | What to do |
| --- | --- | --- |
| MySQL password for PythonAnywhere | `FitnessEmpire/production_setting.py` | Change the database password in the PythonAnywhere dashboard |
| Gmail app password | `FitnessEmpire/settings.py` | Revoke it at <https://myaccount.google.com/apppasswords> and issue a new one |
| Django `SECRET_KEY` | `FitnessEmpire/settings.py` | Generate a new one (below). Sessions and password-reset links signed with the old key must be treated as forgeable |

Generate a fresh signing key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

All three are now read from the environment and nothing is hardcoded, so the
current working tree is clean. Scrubbing them from past commits is a separate,
history-rewriting job that affects everyone who has cloned the repo, so it is
your call whether to do it.

Two more things are tracked in git that you should know about. Neither blocks
the deploy; both are yours to decide on.

- **Compiled bytecode.** About a hundred `__pycache__/*.pyc` files are tracked,
  and the ones built from the old settings still contain the leaked strings.
  They are ignored from now on, but already-tracked files stay tracked. Drop
  them with `git rm -r --cached "**/__pycache__"` and commit.
- **`db.sqlite3`.** It is committed on purpose: it carries the seeded catalogue
  and is what demo mode runs from. It also contains real user rows with hashed
  passwords. Django hashes are not trivially reversible, but if this repository
  is public, tell those users to change their passwords.

---

## 2. Create a database

**The site deploys and runs with nothing set at all.** It comes up in demo
mode: the catalogue, plans and classes are all there, but a wide orange banner
on every page says that nothing anyone does is saved. That is deliberate. A
site that silently discards orders is worse than one that admits it.

Here is why it cannot save anything. Vercel runs the app as a serverless
function. The filesystem is read-only apart from a temp directory, and the
instance is destroyed between requests, so a SQLite file cannot survive: every
sign-up, cart, order and membership goes with it.

To make it a real site, create a free Postgres instance on
[Neon](https://neon.tech), [Supabase](https://supabase.com) or Vercel Postgres,
and copy the connection string. It looks like:

```
postgresql://user:password@host/dbname?sslmode=require
```

Set that as `DATABASE_URL` and the database half of the banner goes away.

---

## 3. Set the environment variables

In the Vercel dashboard, under **Settings → Environment Variables**. The full
list with explanations is in `.env.example`.

Neither of these is required to get the site up, but the banner stays until
both are set:

```
DJANGO_SECRET_KEY    the key you generated in step 1
DATABASE_URL         the connection string from step 2
```

Without `DJANGO_SECRET_KEY` a fresh random key is generated each time a server
instance starts. That is not insecure, but it signs out everyone whenever a new
instance comes up, so logins appear to drop at random.

Worth setting:

```
DJANGO_ALLOWED_HOSTS          your custom domain, comma separated
DJANGO_CSRF_TRUSTED_ORIGINS   the same domains, with https://
EMAIL_HOST_USER               sender address for the password-reset OTP
EMAIL_HOST_PASSWORD           the new app password from step 1
PAYPAL_RECEIVER_EMAIL         your PayPal business address
PAYPAL_TEST                   1 for sandbox, 0 for live money
```

You do not need to set `DJANGO_DEBUG`. Vercel sets `VERCEL=1`, which turns debug
off by itself. The `*.vercel.app` hostnames are accepted automatically, so
preview deployments work without extra configuration.

With no email password set the reset OTP is printed to the Vercel log instead of
sent. That is deliberate, so the flow stays testable rather than erroring.

---

## 4. Deploy

```bash
npm i -g vercel
vercel login
vercel --prod
```

Or connect the GitHub repository in the Vercel dashboard and let it build on
push. Either works; there is no build step to configure.

---

## 5. Migrate

The database starts empty. Run the migrations once, from your machine, pointed
at the same database:

```bash
export DATABASE_URL='postgresql://...'      # the same string Vercel has
export DJANGO_SECRET_KEY='...'
export DJANGO_DEBUG=0

python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data          # optional: plans, classes and products
```

On Windows PowerShell use `$env:DATABASE_URL = '...'` instead of `export`.

---

## What is set up, and why

**Static files** are served by WhiteNoise from inside the Python process. Vercel
puts no web server in front of Django, so without it every stylesheet and image
would 404 as soon as debug was off. It reads through Django's staticfiles
finders, which removes the need for a `collectstatic` build step. If you later
want hashed, permanently cacheable asset URLs, add a build step that runs
`collectstatic` and drop `WHITENOISE_USE_FINDERS` from the settings.

**HTTPS.** Vercel terminates TLS at the edge and forwards plain HTTP, so Django
would otherwise think every request was insecure and build the PayPal return and
IPN URLs as `http://`, breaking the redirect back from PayPal. The settings
trust the forwarding header, so those URLs come out as `https://`.

**Session and CSRF cookies** are marked secure in production. A consequence
worth knowing: if you run the app locally with `DJANGO_DEBUG=0` over plain HTTP,
form submissions will fail CSRF, because the browser will not send a secure
cookie over an insecure connection. That is correct behaviour, not a bug. Test
locally with debug on.

**`mysqlclient` was removed** from the requirements. It is a C extension needing
MySQL headers at build time, which the Vercel image does not have, so the
install failed. Nothing in the project imports it. PythonAnywhere still needs
it: install it there separately and use `FitnessEmpire.production_setting`,
which now reads its credentials from the environment.

---

## The one real limitation

**Uploaded images will not persist.** The product images that ship with the
repository display fine, because they are committed and served from disk. But
anything uploaded through the admin or the product CRUD screen writes to a
read-only filesystem and is gone on the next request.

Fix it when you need uploads, by moving `MEDIA_ROOT` to object storage:

1. Add `django-storages` with an S3, Cloudinary or Vercel Blob backend.
2. Point the `default` entry in `STORAGES` at it.
3. Set `SERVE_MEDIA_FILES=0`, which stops Django serving `/media/` itself.

Until then, treat the catalogue images as fixed. This is a property of
serverless hosting, not of this codebase; the same limit applies to any Django
app on Vercel.

---

## If the deploy 500s

**An orange "Demo mode" banner across the top**: not an error. The site is
running without a database. Set `DATABASE_URL` and `DJANGO_SECRET_KEY` in step
3 and it disappears.

**"Could not find a top-level app" at build time**: `api/index.py` binds `app`
somewhere Vercel's static scan cannot see it, such as inside a `try` block. It
must be a plain top-level assignment. A test guards this.

**Unstyled pages**: WhiteNoise is not running. Check it is still second in
`MIDDLEWARE`, directly after `SecurityMiddleware`.

**`relation "..." does not exist`**: the database is reachable but empty. Run
the migrations in step 5.

**`DisallowedHost`**: you are using a custom domain that is not listed in
`DJANGO_ALLOWED_HOSTS`. The `*.vercel.app` hostnames are handled for you; your
own domain is not.

---

## Checking it worked

After the first deploy:

- The homepage loads and is styled. If the page is unstyled text, WhiteNoise is
  not running; check the middleware order in `settings.py`.
- Product images appear on `/protien/`.
- `/admin/` accepts the superuser you created in step 5.
- Registering an account, then signing out and back in, works. If it does not
  survive a few minutes, you are on the ephemeral database.
- A PayPal checkout redirects to `sandbox.paypal.com` and comes back to your
  domain over HTTPS.
