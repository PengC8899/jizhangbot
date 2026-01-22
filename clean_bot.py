from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./huiying.db"

def clean_bots():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Delete bot with id=2 (TestBot)
        conn.execute(text("DELETE FROM bots WHERE id = 2"))
        conn.commit()
        print("Deleted TestBot (id=2)")

if __name__ == "__main__":
    clean_bots()