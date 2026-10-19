# GovScale
GovScale is a scalable student scholarship and examination portal designed to demonstrate how DevOps practices and AWS cloud infrastructure can help public-service applications handle sudden traffic spikes.

## Setup and Initialization

After installing dependencies and configuring the application, run these
commands from the project root:

```bash
python scripts/seed_institutions.py
python scripts/create_admin.py
```

Use `.venv/bin/python` instead of `python` when using the project virtual
environment.

### Institutions

The institution seeder adds missing institutions by normalized name. It
does not overwrite existing institution records and can be rerun safely.

### Default administrator

The initializer creates this account if its email is not already registered:

- Email: `admin@gmail.com`
- Password: `admin123`

Rerunning it preserves an existing administrator and their password. If the
email belongs to a non-admin account, the script stops without changing it.
Change the default password before exposing the application publicly.

### Redeployment

Run initialization explicitly during setup, not on every application startup.
Keep the database and persistent storage when redeploying application code.
These commands do not import the optional demo JSON data.
