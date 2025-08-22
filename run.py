import os

from app import create_app

# Create the Flask app instance
app = create_app()

if __name__ == "__main__":
    # Flask's built-in development server
    # Hot reloading is enabled via `debug=True` and Docker volume mount.
    app.run(
        debug=app.config.get("DEBUG", True),
        host="0.0.0.0",
        port=int(os.getenv("FLASK_RUN_PORT", 5000)),
    )
