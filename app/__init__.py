"""Flask application factory for Sample Tracker Agent."""

import logging

from flask import Flask

from app import config


def create_app():
    """Create and configure the Flask application."""
    # Ensure INFO-level logs are visible (Python defaults to WARNING)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.FLASK_SECRET_KEY

    # Register routes
    from app.routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    # Initialize database tables (idempotent)
    from app.db.connection import run_migrations
    with app.app_context():
        run_migrations()

    # Start scheduler (only in non-testing mode)
    if not app.config.get("TESTING"):
        from app.scheduler.jobs import start_scheduler
        start_scheduler(app)

    logging.getLogger(__name__).info("Sample Tracker Agent started")
    return app
