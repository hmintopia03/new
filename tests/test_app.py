import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import Base, engine, app
from fastapi.testclient import TestClient

Base.metadata.create_all(bind=engine)

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_targets():
    response = client.get("/targets")
    assert response.status_code == 200