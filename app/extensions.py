# app/extensions.py
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
cors = CORS()  # Initialized here without app, then init_app(app) in __init__
