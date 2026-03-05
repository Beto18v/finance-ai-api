# Define como se crean las tablas en la base de datos utilizando SQLAlchemy. La clase Base es la base para todas las clases de modelos que representan tablas en la base de datos.
from sqlalchemy.orm import declarative_base

Base = declarative_base()