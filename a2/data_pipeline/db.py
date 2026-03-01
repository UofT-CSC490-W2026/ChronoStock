import json
import boto3
from sqlalchemy import create_engine

def get_db_credentials():
    client = boto3.client("secretsmanager", region_name="ca-central-1")
    
    response = client.get_secret_value(
        SecretId="chrono-stock-rds-secret"   
    )
    
    secret = json.loads(response["SecretString"])
    return secret

creds = get_db_credentials()

DB_USER = creds["username"]
DB_PASS = creds["password"]
DB_HOST = creds["host"]
DB_PORT = creds.get("port", "5432")
DB_NAME = creds["dbname"]
API_KEY = creds["polygon_api_key"]

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)