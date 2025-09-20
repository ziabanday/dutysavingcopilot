
from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)

def test_classify_contract():
    r = client.post("/classify", json={})
    assert r.status_code == 200
    data = r.json()
    assert "disclaimer" in data
    assert isinstance(data["codes"], list)
    c = data["codes"][0]
    assert "code" in c and "description" in c and "rationale" in c and "confidence" in c and "evidence" in c
