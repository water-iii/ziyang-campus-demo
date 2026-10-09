from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 导入 main 会实例化供 Uvicorn 使用的全局 app；测试进程让该实例使用内存库，
# 各测试真正操作的仍是下方各自独立的临时 SQLite 文件。
os.environ.setdefault("DATABASE_URL", "sqlite://")

from backend.app.main import create_app


@pytest.fixture()
def workspace_test_dir():
    base_dir = Path(__file__).resolve().parents[2] / ".test-runtime"
    base_dir.mkdir(parents=True, exist_ok=True)
    test_dir = base_dir / uuid.uuid4().hex
    test_dir.mkdir()
    try:
        yield test_dir
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture()
def client(workspace_test_dir):
    database_path = (workspace_test_dir / "test.db").as_posix()
    app = create_app(f"sqlite:///{database_path}")
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()


@pytest.fixture()
def headers():
    def make(role: str, actor: str = "pytest", merchant_id: str | None = None) -> dict[str, str]:
        result = {"X-Demo-Role": role, "X-Demo-Actor": actor}
        if merchant_id:
            result["X-Merchant-Id"] = merchant_id
        return result

    return make
