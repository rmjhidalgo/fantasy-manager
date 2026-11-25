import os
import tempfile

# Use a throwaway data folder so tests never touch real data.
os.environ["FM_DATA_DIR"] = tempfile.mkdtemp(prefix="fm_test_")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["data_dir"] == os.environ["FM_DATA_DIR"]
