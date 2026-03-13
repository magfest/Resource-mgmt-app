"""
Integration tests for routes using Flask test client.
"""


class TestAuthRoutes:
    """Tests for authentication-related routes."""

    def test_home_redirects_when_unauthenticated(self, client):
        """Home page should redirect unauthenticated users to login."""
        response = client.get("/", follow_redirects=False)

        # Should redirect to login page
        assert response.status_code == 302
        assert "/login" in response.location

    def test_login_page_loads(self, client):
        """Login page should load successfully."""
        # Note: /login is the login page, /auth/login initiates OAuth
        response = client.get("/login")

        assert response.status_code == 200
        # Check that the response contains expected login page content
        assert b"Sign" in response.data or b"Login" in response.data or b"sign" in response.data
