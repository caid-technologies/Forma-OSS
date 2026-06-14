import os
import logging
from sqlalchemy import create_engine, Column, String, Float, Integer, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# We default to a PostgreSQL connection, but fall back gracefully to a local SQLite database
# if Postgres is not accessible, to ensure 100% out-of-the-box local reliability.
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:postgres@localhost:5432/blueprint"
)

# SQLite fallback handler
if not DATABASE_URL.startswith("postgresql"):
    # If using local SQLite, make sure to enable multi-threaded access
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
else:
    try:
        engine = create_engine(DATABASE_URL)
        # Quick check connection
        with engine.connect() as conn:
            pass
    except Exception:
        # Fallback to local SQLite if PostgreSQL connection fails
        logger.exception("PostgreSQL connection failed. Falling back to local SQLite 'blueprint.db'.")
        DATABASE_URL = "sqlite:///./blueprint.db"
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DBComponentTemplate(Base):
    __tablename__ = "component_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    part_number = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, default=0.0)
    sourcing_url = Column(String, nullable=True)
    pins = Column(JSON, nullable=False) # List of dict representation of PinDefinition
    use_cases = Column(JSON, nullable=False) # List of strings

class DBGeneratedProject(Base):
    __tablename__ = "generated_projects"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    hardware_ir = Column(JSON, nullable=False) # Dictionary representation of HardwareIR
    created_at = Column(String, nullable=False)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
