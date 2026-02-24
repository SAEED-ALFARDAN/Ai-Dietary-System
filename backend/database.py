from datetime import datetime
import os

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Default: local SQLite file in backend/ folder
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nutrition.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Food(Base):
    __tablename__ = "food"

    food_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # use lowercase class names (e.g. 'burger')
    category = Column(String)
    serving_size = Column(Float)  # grams or ml
    calories = Column(Float)
    protein_g = Column(Float)
    carbs_g = Column(Float)
    fat_g = Column(Float)
    source = Column(String)
    last_updated = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()