# Cada request a la base de datos se maneja a través de una sesión (Session) que se abre al inicio del request y se cierra al final, asegurando que los recursos se liberen adecuadamente.
from sqlalchemy.orm import Session
from .connection import SessionLocal

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()