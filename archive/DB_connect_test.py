# This is a test to see if I can connect to the database
import os
from sqlalchemy import create_engine, text

engine = create_engine(f"postgresql+psycopg2://{os.environ['gcp_username']}:{os.environ['gcp_password']}@{os.environ['gcp_server']}/optionsDB")

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1;"))
    print(result.fetchone())
