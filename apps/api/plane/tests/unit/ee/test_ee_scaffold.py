import pytest
from django.apps import apps
from django.urls import reverse


@pytest.mark.unit
def test_ee_app_installed():
    assert apps.is_installed("plane.ee")


@pytest.mark.unit
@pytest.mark.django_db
def test_ee_urls_mounted(session_client):
    url = reverse("ee-health")
    assert url == "/api/ee/health/"
    resp = session_client.get(url)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
