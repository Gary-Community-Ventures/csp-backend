# app/extensions.py
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

# --- Extensions ---
cors = CORS()
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
