import httpx
import pytest

from companhia.memory import Store


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    # Mesmo havendo .env real na máquina, testes sem transporte falso não podem usar HTTP.
    original = httpx.AsyncClient.__init__

    def guarded(self, *args, **kwargs):
        if kwargs.get("transport") is None:
            raise AssertionError("Rede real proibida nos testes.")
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", guarded)
    monkeypatch.setenv("ROTEIA_API_KEY", "test-only-no-real-key")


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "test.sqlite3")
    yield db
    db.close()
