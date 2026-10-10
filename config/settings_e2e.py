"""Settings for the browser end-to-end tests (run from ../twigaSoft with `npm run test:e2e`).

Uses its own database (E2E_DATABASE_URL, or the DATABASE_URL database name with an `_e2e` suffix),
writes emails to files the tests read, and lifts rate limits so the suite can sign in repeatedly.
"""

import os
from urllib.parse import urlsplit, urlunsplit

if not os.environ.get('E2E_DATABASE_URL'):
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
    base = urlsplit(os.environ['DATABASE_URL'])
    os.environ['E2E_DATABASE_URL'] = urlunsplit(base._replace(path=base.path.rstrip('/') + '_e2e'))
os.environ['DATABASE_URL'] = os.environ['E2E_DATABASE_URL']
os.environ.setdefault('DJANGO_DEBUG', 'true')

from .settings import *  # noqa: E402,F403
from .settings import BASE_DIR, REST_FRAMEWORK  # noqa: E402

E2E = True
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://127.0.0.1:5174').rstrip('/')
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = os.environ.get('E2E_EMAIL_DIR', str(BASE_DIR / '.e2e-mail'))
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_THROTTLE_RATES': {scope: '10000/min' for scope in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']},
}
