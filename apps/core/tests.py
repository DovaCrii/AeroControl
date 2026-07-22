import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.views import serve
from django.test import Client, RequestFactory
from django.urls import reverse


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("admin", "admin@test.com", "admin123")


@pytest.fixture
def auth_client(client, admin_user):
    assert client.login(username="admin", password="admin123")
    return client


class TestPublicURLs:
    """Verify pages that are intentionally available without authentication."""

    def test_login_page(self, client):
        response = client.get(reverse("login"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Sign In" in content
        assert "AeroControl" in content

    def test_login_post_ok(self, client, admin_user):
        response = client.post(
            reverse("login"),
            {"username": "admin", "password": "admin123"},
        )

        assert response.status_code == 302
        assert response.url == "/"

    def test_login_post_invalid(self, client, db):
        response = client.post(
            reverse("login"),
            {"username": "unknown", "password": "wrong"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "Invalid username or password" in content


class TestAuthRequiredURLs:
    """Verify that internal pages require authentication and render for users."""

    AUTH_REQUIRED_URLS = [
        "dashboard",
        "alert-count",
        "costcenter-list",
        "aircraft-list",
        "operator-list",
        "assignment-list",
        "document-list",
        "alert-list",
        "permission-list",
        "record-list",
        "calendar",
        "maintenance-list",
        "task-list",
    ]

    @pytest.mark.parametrize("url_name", AUTH_REQUIRED_URLS)
    def test_requires_login(self, client, url_name):
        response = client.get(reverse(url_name))

        assert response.status_code in (302, 403), (
            f"{url_name} should require login, got {response.status_code}"
        )

    @pytest.mark.parametrize("url_name", AUTH_REQUIRED_URLS)
    def test_returns_success_when_authenticated(self, auth_client, url_name):
        response = auth_client.get(reverse(url_name))

        assert response.status_code in (200, 302), (
            f"{url_name} failed with {response.status_code}"
        )


class TestAuthenticatedPages:
    """Verify representative authenticated pages and shared template behavior."""

    def test_dashboard(self, auth_client):
        response = auth_client.get(reverse("dashboard"))

        assert response.status_code == 200
        assert "Dashboard" in response.content.decode()

    def test_base_template_has_htmx(self, auth_client):
        response = auth_client.get(reverse("dashboard"))

        assert response.status_code == 200
        assert "htmx.org" in response.content.decode()

    def test_base_template_has_dark_mode_toggle(self, auth_client):
        response = auth_client.get(reverse("dashboard"))
        content = response.content.decode()

        assert response.status_code == 200
        assert "toggleTheme" in content
        assert "data-theme" in content
        assert "AeroControl" in content

    def test_dashboard_serializes_chart_data_without_marking_it_safe(self, auth_client):
        response = auth_client.get(reverse("dashboard"))
        content = response.content.decode()

        assert 'id="chart-data" type="application/json"' in content
        assert "chart_data|safe" not in content

    def test_logout_requires_post_and_logs_out(self, auth_client):
        response = auth_client.post(reverse("logout"))

        assert response.status_code == 302
        assert response.url == reverse("login")

    def test_language_switches_navigation_and_status_labels_to_spanish(self, auth_client):
        response = auth_client.post(
            reverse("set_language"), {"language": "es", "next": reverse("dashboard")}
        )

        assert response.status_code == 302
        response = auth_client.get(reverse("dashboard"))
        assert "Panel de operaciones" in response.content.decode()
        assert "Aeronaves" in response.content.decode()


class TestStaticFiles:
    def test_css_is_served(self):
        static_path = finders.find("css/app.css")

        assert static_path is not None
        request = RequestFactory().get(f"{settings.STATIC_URL.rstrip('/')}/css/app.css")
        response = serve(request, "css/app.css", insecure=True)

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/css")
