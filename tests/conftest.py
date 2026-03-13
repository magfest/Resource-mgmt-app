"""
Shared pytest fixtures for the MAGFest Budget application.
"""
import pytest
from app import create_app, db


@pytest.fixture(scope="function")
def app():
    """Create a Flask application configured for testing."""
    test_app = create_app()

    # Override configuration for testing
    test_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "DEV_LOGIN_ENABLED": False,  # Disable to avoid demo seeding issues
        "SECRET_KEY": "test-secret-key",
    })

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """Create a Flask test client for HTTP requests."""
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app):
    """Provide a database session with automatic rollback."""
    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture(scope="function")
def authenticated_client(app, client):
    """Create a client with session configured for a test user."""
    with client.session_transaction() as sess:
        sess["active_user_id"] = "dev:admin"
    return client
