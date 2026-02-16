# Environment: 

```source .venv/bin/activate```

# About database:
Step to start and initialize database:
1. Start PostgreSQL server (Container or local)
2. Create database with name.
3. Run `alembic upgrade head` to create tables.

Step to do migrations:
1. Edit models.py
2. alembic revision --autogenerate -m "your message"
3. alembic upgrade head

Step to drop database:
1. Drop database with name (What do you expect?)
2. (Optional) Probably clear and recreate the alembic folder to reset migration history. (rm -rf alembic)