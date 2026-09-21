from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Para desarrollo local usamos SQLite. 
# En producción, esta cadena cambiará a: "postgresql://usuario:clave@servidor/bd_asecob"
SQLALCHEMY_DATABASE_URL = "sqlite:///./asecob_legaltech.db"

# connect_args solo es necesario para SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()