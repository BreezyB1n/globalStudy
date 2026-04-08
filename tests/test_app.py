import importlib
import sys

from fastapi.testclient import TestClient


def _load_main_module():
    for module_name in ("app.main", "app.core.config"):
        sys.modules.pop(module_name, None)
    return importlib.import_module("app.main")


def test_health_endpoint_returns_basic_status(app_env, project_root):
    main = _load_main_module()
    client = TestClient(main.create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "GlobalStudy AI",
        "env": "dev",
    }
    assert response.headers["x-request-id"]
    assert (project_root / "data" / "raw").exists()
    assert (project_root / "data" / "processed").exists()
    assert (project_root / "data" / "sqlite").exists()
    assert (project_root / "data" / "chroma").exists()
    assert (project_root / "logs").exists()


def test_root_serves_placeholder_frontend(app_env):
    main = _load_main_module()
    client = TestClient(main.create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "GlobalStudy AI" in response.text


def test_static_assets_are_served(app_env):
    main = _load_main_module()
    client = TestClient(main.create_app())

    js_response = client.get("/assets/app.js")
    css_response = client.get("/assets/styles.css")

    assert js_response.status_code == 200
    assert "javascript" in js_response.headers["content-type"]
    assert css_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]


def test_api_not_found_uses_json_error_shape(app_env):
    main = _load_main_module()
    client = TestClient(main.create_app())

    response = client.get("/api/not-found")

    body = response.json()
    assert response.status_code == 404
    assert body["code"] == "NOT_FOUND"
    assert body["message"] == "API route not found"
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]


def test_unhandled_api_errors_use_unified_json_response(app_env):
    main = _load_main_module()
    app = main.create_app()

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/boom")

    body = response.json()
    assert response.status_code == 500
    assert body["code"] == "INTERNAL_SERVER_ERROR"
    assert body["message"] == "Internal server error"
    assert body["request_id"]
