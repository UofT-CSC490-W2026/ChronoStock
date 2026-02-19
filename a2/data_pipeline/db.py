import os
from sqlalchemy import create_engine

DB_USER = os.getenv("RDS_USER")
DB_PASS = os.getenv("RDS_PASS")
DB_HOST = os.getenv("RDS_HOST")
DB_PORT = os.getenv("RDS_PORT", "5432")
DB_NAME = os.getenv("RDS_DB")

if not all([DB_USER, DB_PASS, DB_HOST, DB_NAME]):
    raise ValueError("Database environment variables are not set properly.")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
