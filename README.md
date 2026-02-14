# Environment: 

```source .venv/bin/activate```

# About database:
Step to do migrations:
1. Edit models.py
2. alembic revision --autogenerate -m "your message"
3. alembic upgrade head