import os

from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["data_dir"] == os.environ["FM_DATA_DIR"]
