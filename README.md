# twigaSoftApi

Django + Django REST Framework API for the AFRIGULF Exchange site (frontend: `../twigaSoft`).

## Setup

Requires MySQL 8.0.13+ and the MySQL client libraries (`brew install mysql-client pkgconf` on macOS).

Create the database and a user (in `mysql -u root`):

```sql
CREATE DATABASE twigasoft CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'twigasoft'@'localhost' IDENTIFIED BY 'change-me';
GRANT ALL PRIVILEGES ON twigasoft.* TO 'twigasoft'@'localhost';
GRANT ALL PRIVILEGES ON test_twigasoft.* TO 'twigasoft'@'localhost';  -- for manage.py test
```

```bash
python3 -m venv .venv
# Homebrew's mysql-client is keg-only, so point the mysqlclient build at it:
PKG_CONFIG_PATH="$(brew --prefix mysql-client)/lib/pkgconfig" .venv/bin/pip install -r requirements.txt
cp .env.example .env            # then set DJANGO_SECRET_KEY and DATABASE_URL
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser   # this account can sign in at /admin/login on the site
.venv/bin/python manage.py runserver 8000
```

The frontend dev server (`npm run dev` in `../twigaSoft`) proxies `/api` to `http://localhost:8000`.
In development, emails (password reset links) are printed to the `runserver` terminal.

Run the tests with `.venv/bin/python manage.py test`.

## Endpoints

Errors are a non-2xx status with `{ "error": "<message for the user>", "fields": { "<field>": ["…"] } }`
(`fields` only appears for field validation errors).

| Method & path | Auth | Body | Response |
| --- | --- | --- | --- |
| `GET /api/events` | – | – | `{ events: [{ slug, title, location, period, organiser, summary, label, image }] }` |
| `POST /api/enquiries` | – | `{ name, email, phone?, country, interest, message, website? }` | `201 { reference }` |
| `POST /api/admin/auth/login` | – | `{ email, password }` | `{ token, admin: { id, email, name } }` |
| `POST /api/admin/auth/logout` | Bearer | – | `204` |
| `GET /api/admin/auth/me` | Bearer | – | `{ admin }` |
| `POST /api/admin/auth/forgot-password` | – | `{ email }` | `200`, the same whether or not the account exists |
| `POST /api/admin/auth/reset-password` | – | `{ token, password }` | `200` |

- **Admins** are `accounts.User` records (a custom user model with email as the unique, case-insensitive login field) with `is_staff` set.
- **Tokens** are sent as `Authorization: Bearer <token>`. Each admin has one token; signing in replaces it,
  and it expires after `ADMIN_TOKEN_TTL_HOURS` (default 12).
- **Password reset** emails link to `FRONTEND_URL/admin/reset-password?token=…`. Links expire after
  `PASSWORD_RESET_TIMEOUT` seconds (default 1 hour) and stop working once used, or once the admin signs in again.
  A successful reset signs the admin out everywhere. Django's password validators apply.
- **Enquiries**: a filled-in `website` honeypot gets a normal-looking response but nothing is stored.
- **Rate limits** per IP: login 10/min, forgot password 5/hour, reset 20/hour, enquiries 20/hour.

## Managing content

Django's admin is at `/django-admin/` (sign in with a staff account). Use it to add or edit events,
which the site shows in order of `sort_order`, and to view enquiries and track their status.

## Production

Set `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL` (`mysql://user:pass@host:3306/db`),
`FRONTEND_URL`, SMTP settings, and `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` if the site and API
are on different origins. Run `manage.py collectstatic` and serve with a WSGI server such as gunicorn.
The rate limits use Django's cache; configure a shared cache (e.g. Redis) if you run several processes.
