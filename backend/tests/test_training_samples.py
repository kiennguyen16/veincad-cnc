from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.auth import get_db
from app.config import Settings
from app.database import Database
from app.main import app, app_db, app_settings


def _png_bytes(value: int = 180) -> bytes:
    image = np.full((32, 48, 3), value, dtype=np.uint8)
    cv2.line(image, (3, 25), (44, 5), (20, 20, 20), 2)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


@pytest.fixture
def training_client(tmp_path: Path):
    storage_root = tmp_path / "storage"
    settings = Settings(
        storage_dir=storage_root,
        sample_dir=tmp_path / "samples",
        database_path=storage_root / "test.sqlite3",
        upload_dir=storage_root / "uploads" / "slabs",
    )
    settings.training_dir.mkdir(parents=True)
    settings.sample_dir.mkdir(parents=True)
    settings.upload_dir.mkdir(parents=True)

    database = Database(settings.database_path)
    database.init(settings)
    admin = database.get_user_by_email(settings.seed_admin_email)
    assert admin is not None
    admin_token, _ = database.create_session(admin["id"], settings.session_days)
    regular_user = database.create_user(email="worker@example.com", password="secret123")
    regular_token, _ = database.create_session(regular_user["id"], settings.session_days)

    app.dependency_overrides[app_settings] = lambda: settings
    app.dependency_overrides[app_db] = lambda: database
    app.dependency_overrides[get_db] = lambda: database
    with TestClient(app) as client:
        yield client, database, settings, admin_token, regular_token
    app.dependency_overrides.clear()


def test_training_sample_admin_lifecycle(training_client) -> None:
    client, database, settings, admin_token, _ = training_client
    client.cookies.set(settings.auth_cookie_name, admin_token)

    response = client.post(
        "/api/v1/training/samples",
        data={"style_id": "centerline", "notes": "Clean hand-traced center line"},
        files={
            "source_image": ("../source.png", _png_bytes(190), "image/png"),
            "label_image": ("label.png", _png_bytes(255), "image/png"),
        },
    )
    assert response.status_code == 201
    sample = response.json()
    assert set(sample) == {
        "id",
        "style_id",
        "source_original_filename",
        "label_original_filename",
        "source_image_url",
        "label_image_url",
        "notes",
        "status",
        "created_at",
        "created_by",
    }
    assert sample["source_original_filename"] == "source.png"
    assert sample["style_id"] == "centerline"
    assert sample["status"] == "uploaded"
    stored = database.get_training_sample(sample_id=sample["id"])
    assert stored is not None
    assert stored["source_path"].startswith(f"training/centerline/{sample['id']}/")
    assert (settings.storage_root / stored["source_path"]).is_file()
    assert (settings.storage_root / stored["label_path"]).is_file()

    listed = client.get("/api/training/samples").json()
    assert [item["id"] for item in listed] == [sample["id"]]

    summary = client.get("/api/v1/training/summary")
    assert summary.status_code == 200
    assert set(summary.json()) == {
        "total_samples",
        "counts_by_style",
        "required_per_style",
        "ready_to_train",
        "status",
    }
    assert summary.json()["counts_by_style"] == {"centerline": 1, "high_detail": 0}
    assert summary.json()["required_per_style"] == 20
    assert summary.json()["ready_to_train"] is False
    assert summary.json()["status"] == "not_ready"

    source_media = client.get(sample["source_image_url"])
    assert source_media.status_code == 200
    assert source_media.headers["content-type"] == "image/png"

    deleted = client.delete(f"/api/v1/training/samples/{sample['id']}")
    assert deleted.status_code == 200
    assert database.get_training_sample(sample_id=sample["id"]) is None
    assert not (settings.training_dir / "centerline" / sample["id"]).exists()


def test_training_endpoints_require_admin(training_client) -> None:
    client, _, settings, _, regular_token = training_client

    assert client.get("/api/v1/training/summary").status_code == 401
    client.cookies.set(settings.auth_cookie_name, regular_token)
    assert client.get("/api/v1/training/summary").status_code == 403


def test_training_upload_rejects_invalid_style_and_unreadable_image(training_client) -> None:
    client, _, settings, admin_token, _ = training_client
    client.cookies.set(settings.auth_cookie_name, admin_token)
    valid_image = _png_bytes()

    invalid_style = client.post(
        "/api/v1/training/samples",
        data={"style_id": "../centerline"},
        files={
            "source_image": ("source.png", valid_image, "image/png"),
            "label_image": ("label.png", valid_image, "image/png"),
        },
    )
    assert invalid_style.status_code == 400

    unreadable = client.post(
        "/api/v1/training/samples",
        data={"style_id": "high_detail"},
        files={
            "source_image": ("source.png", b"not an image", "image/png"),
            "label_image": ("label.png", valid_image, "image/png"),
        },
    )
    assert unreadable.status_code == 400
    assert list(settings.training_dir.rglob("*")) == []
