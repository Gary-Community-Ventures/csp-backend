from app import create_app

# Create the Flask app instance for the WSGI server
app = create_app()

# This is the entry point that Gunicorn (or other WSGI servers) will look for.
