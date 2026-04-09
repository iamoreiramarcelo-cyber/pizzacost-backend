"""Shared fixtures for PizzaCost Pro backend tests."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt

# ---------------------------------------------------------------------------
# Environment variables required by Settings (set BEFORE any app import)
# ---------------------------------------------------------------------------
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "super-secret-jwt-key-for-testing-only")
os.environ.setdefault("MERCADOPAGO_WEBHOOK_SECRET", "mp-webhook-secret-for-testing")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("API_RATE_LIMIT", "1000/minute")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]
JWT_ALGORITHM = "HS256"

TEST_USER_ID = str(uuid4())
TEST_USER_EMAIL = "testuser@example.com"

TEST_ADMIN_ID = str(uuid4())
TEST_ADMIN_EMAIL = "admin@example.com"

TEST_USER_B_ID = str(uuid4())
TEST_USER_B_EMAIL = "userb@example.com"

INSUMO_ID = str(uuid4())
TAMANHO_ID = str(uuid4())
BORDA_ID = str(uuid4())
PIZZA_ID = str(uuid4())
COMBO_ID = str(uuid4())

NOW_ISO = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# JWT helper
# ---------------------------------------------------------------------------

def create_test_jwt(
    user_id: str,
    role: str = "user",
    email: str = "test@example.com",
    expired: bool = False,
) -> str:
    """Create a signed HS256 JWT compatible with the app's auth middleware."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "aud": "authenticated",
        "iat": now,
        "exp": (now - 3600) if expired else (now + 3600),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Mock Supabase client
# ---------------------------------------------------------------------------

class _MockQueryBuilder:
    """Chainable mock that mimics Supabase's PostgREST query builder."""

    def __init__(self, data: list[dict] | None = None, count: int | None = None):
        self._data = data or []
        self._count = count

    # --- chainable methods ---
    def select(self, *args: Any, **kwargs: Any) -> "_MockQueryBuilder":
        return self

    def insert(self, payload: Any) -> "_MockQueryBuilder":
        if isinstance(payload, list):
            self._data = payload
        else:
            self._data = [payload]
        return self

    def update(self, payload: Any) -> "_MockQueryBuilder":
        if self._data:
            self._data = [{**self._data[0], **payload}]
        else:
            self._data = [payload]
        return self

    def delete(self) -> "_MockQueryBuilder":
        return self

    def eq(self, *args: Any) -> "_MockQueryBuilder":
        return self

    def neq(self, *args: Any) -> "_MockQueryBuilder":
        return self

    def in_(self, *args: Any) -> "_MockQueryBuilder":
        return self

    def gte(self, *args: Any) -> "_MockQueryBuilder":
        return self

    def lte(self, *args: Any) -> "_MockQueryBuilder":
        return self

    def or_(self, *args: Any) -> "_MockQueryBuilder":
        return self

    def order(self, *args: Any, **kwargs: Any) -> "_MockQueryBuilder":
        return self

    def range(self, *args: Any) -> "_MockQueryBuilder":
        return self

    def maybe_single(self) -> "_MockQueryBuilder":
        return self

    def execute(self) -> "_MockResult":
        return _MockResult(data=self._data, count=self._count)


class _MockResult:
    def __init__(self, data: list[dict], count: int | None = None):
        self.data = data
        self.count = count if count is not None else len(data)


class _MockAuth:
    class admin:
        @staticmethod
        def create_user(payload: dict) -> Any:
            user = MagicMock()
            user.id = str(uuid4())
            result = MagicMock()
            result.user = user
            return result


class MockSupabaseClient:
    """A lightweight mock for the Supabase Python client."""

    def __init__(self) -> None:
        self.auth = _MockAuth()
        self._tables: dict[str, _MockQueryBuilder] = {}
        self.storage = MagicMock()

    def configure_table(
        self,
        table_name: str,
        data: list[dict] | None = None,
        count: int | None = None,
    ) -> None:
        """Pre-configure the data that ``table(name)`` will return."""
        self._tables[table_name] = _MockQueryBuilder(data=data, count=count)

    def table(self, name: str) -> _MockQueryBuilder:
        if name in self._tables:
            return self._tables[name]
        return _MockQueryBuilder()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_db() -> MockSupabaseClient:
    """Return a fresh mock Supabase client."""
    db = MockSupabaseClient()
    # Pre-configure common tables with sensible defaults
    db.configure_table("profiles", data=[{
        "id": TEST_USER_ID,
        "email": TEST_USER_EMAIL,
        "nome_loja": "Pizzaria Teste",
        "telefone": "+5511999999999",
        "role": "user",
        "subscription_status": "free",
        "subscription_expires_at": None,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }], count=1)
    db.configure_table("insumos", data=[], count=0)
    db.configure_table("tamanhos", data=[], count=0)
    db.configure_table("bordas", data=[], count=0)
    db.configure_table("pizzas", data=[], count=0)
    db.configure_table("combos", data=[], count=0)
    db.configure_table("consent_logs", data=[], count=0)
    db.configure_table("email_preferences", data=[], count=0)
    db.configure_table("lgpd_requests", data=[], count=0)
    db.configure_table("payment_logs", data=[], count=0)
    db.configure_table("subscription_history", data=[], count=0)
    db.configure_table("user_activity", data=[], count=0)
    db.configure_table("audit_logs", data=[], count=0)
    return db


@pytest.fixture()
def app(mock_db: MockSupabaseClient):
    """Create a FastAPI test app with mocked dependencies."""
    from app.config import get_settings

    # Clear the LRU cache so test env vars take effect
    get_settings.cache_clear()

    from app.database import get_supabase_client
    from app.middleware.auth import get_current_user, require_admin, UserContext
    from main import create_app

    application = create_app()

    # Override the DB dependency wherever it is injected
    def _override_db():
        return mock_db

    def _override_user():
        return UserContext(id=TEST_USER_ID, email=TEST_USER_EMAIL, role="user")

    def _override_admin():
        return UserContext(id=TEST_ADMIN_ID, email=TEST_ADMIN_EMAIL, role="admin")

    application.dependency_overrides[get_supabase_client] = _override_db
    application.dependency_overrides[get_current_user] = _override_user
    application.dependency_overrides[require_admin] = _override_admin

    return application


@pytest_asyncio.fixture()
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Authorization header with a valid regular-user JWT."""
    token = create_test_jwt(TEST_USER_ID, role="user", email=TEST_USER_EMAIL)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    """Authorization header with a valid admin JWT."""
    token = create_test_jwt(TEST_ADMIN_ID, role="admin", email=TEST_ADMIN_EMAIL)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def sample_insumo() -> dict:
    return {
        "id": INSUMO_ID,
        "user_id": TEST_USER_ID,
        "nome": "Mussarela",
        "unidade": "kg",
        "preco": 42.90,
        "quantidade_comprada": 1.0,
        "custo_unitario": 42.90,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }


@pytest.fixture()
def sample_tamanho() -> dict:
    return {
        "id": TAMANHO_ID,
        "user_id": TEST_USER_ID,
        "nome": "Grande",
        "preco_total": 15.00,
        "quantidade_embalagens": 10,
        "custo_embalagem": 1.50,
        "custo_massa": 3.50,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }


@pytest.fixture()
def sample_borda() -> dict:
    return {
        "id": BORDA_ID,
        "user_id": TEST_USER_ID,
        "nome": "Catupiry",
        "tamanho_id": TAMANHO_ID,
        "preco_venda": 8.00,
        "ingredientes": [
            {"insumo_id": INSUMO_ID, "quantidade": 0.15, "unidade": "kg"},
        ],
        "custo_calculado": 6.44,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }


@pytest.fixture()
def sample_pizza() -> dict:
    return {
        "id": PIZZA_ID,
        "user_id": TEST_USER_ID,
        "nome": "Margherita",
        "tamanho_id": TAMANHO_ID,
        "borda_id": None,
        "ingredientes": [
            {"insumo_id": INSUMO_ID, "quantidade": 0.25, "unidade": "kg"},
        ],
        "custo_adicionais": 1.50,
        "preco_venda": 45.00,
        "custo_calculado": 15.73,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }


@pytest.fixture()
def sample_combo() -> dict:
    return {
        "id": COMBO_ID,
        "user_id": TEST_USER_ID,
        "nome": "Combo Familia",
        "pizzas": [
            {"pizza_id": PIZZA_ID, "quantidade": 2},
        ],
        "outros_custos": 5.00,
        "preco_venda_sugerido": 120.00,
        "custo_calculado": 36.46,
        "margem_lucro": 69.6,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }
