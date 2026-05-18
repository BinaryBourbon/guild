# Deployment

## Database URL coercion (Render / Heroku)

Render's managed Postgres service supplies `DATABASE_URL` with a `postgres://`
or `postgresql://` scheme. SQLAlchemy's default dialect resolution maps those
prefixes to psycopg2, but Guild depends on psycopg3 (`psycopg>=3.1`) and does
not install psycopg2. To prevent a "could not load driver" failure at startup,
`guild.db._coerce_psycopg3()` rewrites those prefixes to
`postgresql+psycopg://` before the URL reaches SQLAlchemy. The same coercion
is applied in `migrations/env.py` so that `alembic upgrade head` on Render
also works correctly. URLs that already carry an explicit driver string (e.g.
`postgresql+psycopg://` or `postgresql+psycopg2://`) are left unchanged.
