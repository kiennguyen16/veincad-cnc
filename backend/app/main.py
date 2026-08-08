from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated
import uuid

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.auth import (
    authenticate_user,
    clear_session_cookie,
    current_user,
    get_db,
    public_user,
    set_session_cookie,
)
from app.cad_chat import apply_dxf_actions, plan_dxf_actions
from app.config import Settings, get_settings
from app.database import Database
from app.email_service import password_reset_link, send_password_reset_email
from app.image_config import plan_processing_settings
from app.models import (
    AdminCreateUserRequest,
    AdminSummary,
    AuthResponse,
    CreateFolderRequest,
    DxfChatMessage,
    DxfModifyRequest,
    DxfModifyResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ProcessingConfigureRequest,
    ProcessingConfigureResponse,
    ProcessingSettingsSuggestion,
    ProcessResponse,
    ResetPasswordRequest,
    SampleImage,
    StorageFolder,
    StyleResponse,
    TrainingSampleResponse,
    TrainingSummaryResponse,
    UploadRecord,
    UserResponse,
)
from app.pipeline.processing import ProcessingRequest, load_manifest, process_upload
from app.pipeline.segmentation import Sam2Segmenter
from app.pipeline.styles import STYLES
from app.training_data import (
    TRAINING_READINESS_THRESHOLD,
    TRAINING_STYLE_IDS,
    persist_training_pair,
    remove_training_sample_files,
    resolve_training_file,
    validate_training_image,
)

app = FastAPI(title="VeinCAD CNC API", version="0.1.0")

settings = get_settings()
db = get_db()
db.init(settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PublicStorageFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict) -> Response:
        first_segment = path.replace("\\", "/").lstrip("/").split("/", 1)[0].lower()
        if first_segment == "training":
            return Response(status_code=404)
        return await super().get_response(path, scope)


app.mount("/storage", PublicStorageFiles(directory=settings.storage_dir), name="storage")
app.mount("/sample_images", StaticFiles(directory=settings.sample_dir), name="sample_images")

segmenter = Sam2Segmenter(settings)
ADMIN_EMAIL = "slokermoliti@gmail.com"
JOB_STORAGE_RESERVE_BYTES = 512 * 1024 * 1024
DXF_REVISION_STORAGE_RESERVE_BYTES = 64 * 1024 * 1024


def app_settings() -> Settings:
    return settings


def app_db() -> Database:
    return db


@app.get("/health")
@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return {"ok": True, "sam2_available": segmenter.available}


@app.post("/api/auth/login", response_model=AuthResponse)
@app.post("/api/v1/auth/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
) -> AuthResponse:
    user = authenticate_user(database, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token, _ = database.create_session(user["id"], config.session_days)
    set_session_cookie(response, config, token)
    return AuthResponse(user=UserResponse(**public_user(user)))


@app.post("/api/auth/forgot-password", response_model=MessageResponse)
@app.post("/api/v1/auth/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
) -> MessageResponse:
    email = payload.email.strip().lower()
    user = database.get_user_by_email(email)
    if user is not None:
        token, _ = database.create_password_reset_token(
            user_id=user["id"],
            expires_minutes=config.password_reset_minutes,
        )
        reset_link = password_reset_link(config, token)
        try:
            await run_in_threadpool(
                send_password_reset_email,
                settings=config,
                email=email,
                reset_link=reset_link,
            )
        except Exception as exc:
            print(f"Password reset email failed for {email}: {exc}")

    return MessageResponse(
        ok=True,
        message="If an account exists for that email, a password reset link has been sent.",
    )


@app.post("/api/auth/reset-password", response_model=MessageResponse)
@app.post("/api/v1/auth/reset-password", response_model=MessageResponse)
def reset_password(
    payload: ResetPasswordRequest,
    database: Annotated[Database, Depends(app_db)],
) -> MessageResponse:
    user = database.reset_password_with_token(token=payload.token.strip(), password=payload.password)
    if user is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    return MessageResponse(ok=True, message="Your password has been reset. You can sign in now.")


@app.post("/api/auth/logout")
@app.post("/api/v1/auth/logout")
def logout(
    response: Response,
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
    veincad_session: Annotated[str | None, Cookie(alias="veincad_session")] = None,
) -> dict[str, bool]:
    if veincad_session:
        database.delete_session(veincad_session)
    clear_session_cookie(response, config)
    return {"ok": True}


@app.get("/api/auth/me", response_model=AuthResponse)
@app.get("/api/v1/auth/me", response_model=AuthResponse)
def me(user: Annotated[dict, Depends(current_user)]) -> AuthResponse:
    return AuthResponse(user=UserResponse(**public_user(user)))


def _require_admin(user: dict) -> None:
    if str(user["email"]).lower() != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Only the site administrator can access this page.")


@app.get("/api/admin/summary", response_model=AdminSummary)
@app.get("/api/v1/admin/summary", response_model=AdminSummary)
def admin_summary(
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> AdminSummary:
    _require_admin(user)

    summary = database.admin_summary()
    storage_bytes = _directory_size(config.storage_dir)
    storage_available_bytes = max(config.storage_quota_bytes - storage_bytes, 0)
    storage_usage_percent = (
        round((storage_bytes / config.storage_quota_bytes) * 100, 2)
        if config.storage_quota_bytes > 0
        else 0
    )
    return AdminSummary(
        admin_email=ADMIN_EMAIL,
        job_count=_job_count(config.storage_dir),
        storage_bytes=storage_bytes,
        storage_quota_bytes=config.storage_quota_bytes,
        storage_available_bytes=storage_available_bytes,
        storage_usage_percent=storage_usage_percent,
        storage_path=str(config.storage_dir),
        **summary,
    )


@app.post("/api/admin/users", response_model=UserResponse)
@app.post("/api/v1/admin/users", response_model=UserResponse)
def create_admin_user(
    payload: AdminCreateUserRequest,
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> UserResponse:
    _require_admin(user)

    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    try:
        created_user = database.create_user(email=email, password=payload.password, role="user")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return UserResponse(**public_user(created_user))


@app.post("/api/training/samples", response_model=TrainingSampleResponse, status_code=201)
@app.post("/api/v1/training/samples", response_model=TrainingSampleResponse, status_code=201)
async def create_training_sample(
    source_image: Annotated[UploadFile, File()],
    label_image: Annotated[UploadFile, File()],
    style_id: Annotated[str, Form()],
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
    notes: Annotated[str | None, Form()] = None,
) -> TrainingSampleResponse:
    _require_admin(user)
    if style_id not in TRAINING_STYLE_IDS:
        raise HTTPException(
            status_code=400,
            detail="style_id must be exactly 'centerline' or 'high_detail'.",
        )

    source_bytes = await source_image.read(config.max_upload_bytes + 1)
    label_bytes = await label_image.read(config.max_upload_bytes + 1)
    if not source_bytes or not label_bytes:
        raise HTTPException(status_code=400, detail="Both source_image and label_image are required.")
    if len(source_bytes) > config.max_upload_bytes or len(label_bytes) > config.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Each training image must be no larger than {config.max_upload_mb} MB.",
        )
    _ensure_storage_quota(
        config,
        additional_bytes=len(source_bytes) + len(label_bytes),
        operation="training sample upload",
    )

    clean_notes = notes.strip() if notes and notes.strip() else None
    if clean_notes and len(clean_notes) > 4000:
        raise HTTPException(status_code=400, detail="notes must be 4000 characters or fewer.")

    try:
        source_name, source_suffix = validate_training_image(
            source_bytes,
            source_image.filename,
            "source_image",
        )
        label_name, label_suffix = validate_training_image(
            label_bytes,
            label_image.filename,
            "label_image",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sample_id = uuid.uuid4().hex
    stored_files = None
    try:
        stored_files = persist_training_pair(
            storage_root=config.storage_root,
            style_id=style_id,
            sample_id=sample_id,
            source_bytes=source_bytes,
            source_original_filename=source_name,
            source_suffix=source_suffix,
            label_bytes=label_bytes,
            label_original_filename=label_name,
            label_suffix=label_suffix,
        )
        record = database.create_training_sample(
            sample_id=sample_id,
            source_original_filename=stored_files.source_original_filename,
            source_stored_filename=stored_files.source_stored_filename,
            source_path=stored_files.source_path,
            label_original_filename=stored_files.label_original_filename,
            label_stored_filename=stored_files.label_stored_filename,
            label_path=stored_files.label_path,
            style_id=style_id,
            notes=clean_notes,
            status="uploaded",
            created_by=user["id"],
        )
    except Exception:
        sample_dir = config.training_dir / style_id / sample_id
        if sample_dir.exists() and stored_files is not None:
            remove_training_sample_files(
                config.storage_root,
                {
                    "id": sample_id,
                    "style_id": style_id,
                    "source_path": stored_files.source_path,
                    "source_stored_filename": stored_files.source_stored_filename,
                    "label_path": stored_files.label_path,
                    "label_stored_filename": stored_files.label_stored_filename,
                },
            )
        raise

    return _training_sample_response(record)


@app.get("/api/training/samples", response_model=list[TrainingSampleResponse])
@app.get("/api/v1/training/samples", response_model=list[TrainingSampleResponse])
def list_training_samples(
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
    style_id: str | None = None,
) -> list[TrainingSampleResponse]:
    _require_admin(user)
    if style_id is not None and style_id not in TRAINING_STYLE_IDS:
        raise HTTPException(
            status_code=400,
            detail="style_id must be exactly 'centerline' or 'high_detail'.",
        )
    return [
        _training_sample_response(record)
        for record in database.list_training_samples(style_id=style_id)
    ]


@app.get("/api/training/summary", response_model=TrainingSummaryResponse)
@app.get("/api/v1/training/summary", response_model=TrainingSummaryResponse)
def training_summary(
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> TrainingSummaryResponse:
    _require_admin(user)
    stored_counts = database.training_sample_counts()
    counts = {style_id: stored_counts.get(style_id, 0) for style_id in TRAINING_STYLE_IDS}
    ready_to_train = all(
        count >= TRAINING_READINESS_THRESHOLD for count in counts.values()
    )
    return TrainingSummaryResponse(
        total_samples=sum(counts.values()),
        counts_by_style=counts,
        required_per_style=TRAINING_READINESS_THRESHOLD,
        ready_to_train=ready_to_train,
        status="ready" if ready_to_train else "not_ready",
    )


@app.get("/api/training/samples/{sample_id}/{image_kind}")
@app.get("/api/v1/training/samples/{sample_id}/{image_kind}")
def get_training_sample_image(
    sample_id: str,
    image_kind: str,
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> FileResponse:
    _require_admin(user)
    record = database.get_training_sample(sample_id=sample_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Training sample not found.")
    try:
        image_path = resolve_training_file(config.storage_root, record, image_kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Training image file not found.")
    media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    return FileResponse(image_path, media_type=media_type)


@app.delete("/api/training/samples/{sample_id}", response_model=MessageResponse)
@app.delete("/api/v1/training/samples/{sample_id}", response_model=MessageResponse)
def delete_training_sample(
    sample_id: str,
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> MessageResponse:
    _require_admin(user)
    record = database.get_training_sample(sample_id=sample_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Training sample not found.")
    try:
        remove_training_sample_files(config.storage_root, record)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not database.delete_training_sample(sample_id=sample_id):
        raise HTTPException(status_code=404, detail="Training sample not found.")
    return MessageResponse(ok=True, message="Training sample deleted.")


@app.get("/api/styles", response_model=list[StyleResponse])
@app.get("/api/v1/styles", response_model=list[StyleResponse])
def list_styles(user: Annotated[dict, Depends(current_user)]) -> list[StyleResponse]:
    return [
        StyleResponse(
            id=style.id,
            name=style.name,
            summary=style.summary,
            output_mode=style.output_mode,
            default_sensitivity=style.default_sensitivity,
            default_noise_filter=style.default_noise_filter,
            default_simplify_tolerance=style.default_simplify_tolerance,
        )
        for style in (STYLES["centerline"], STYLES["high_detail"])
    ]


@app.get("/api/samples", response_model=list[SampleImage])
@app.get("/api/v1/samples", response_model=list[SampleImage])
def list_samples(
    config: Annotated[Settings, Depends(app_settings)],
    user: Annotated[dict, Depends(current_user)],
) -> list[SampleImage]:
    extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    samples: list[SampleImage] = []
    for path in sorted(config.sample_dir.iterdir()):
        if path.suffix.lower() not in extensions:
            continue
        samples.append(SampleImage(name=path.name, url=f"/sample_images/{path.name}"))
    return samples


@app.get("/api/uploads", response_model=list[UploadRecord])
@app.get("/api/v1/uploads", response_model=list[UploadRecord])
def list_uploads(
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
    folder_id: str | None = None,
) -> list[UploadRecord]:
    records = database.list_uploads(user_id=user["id"], folder_id=folder_id)
    for item in records:
        item["source_image_url"] = _storage_url(config.storage_dir, Path(item["file_path"]))
    return [UploadRecord(**item) for item in records]


@app.get("/api/storage/folders", response_model=list[StorageFolder])
@app.get("/api/v1/storage/folders", response_model=list[StorageFolder])
def list_storage_folders(
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> list[StorageFolder]:
    return [StorageFolder(**item) for item in database.list_folders(user_id=user["id"])]


@app.post("/api/storage/folders", response_model=StorageFolder)
@app.post("/api/v1/storage/folders", response_model=StorageFolder)
def create_storage_folder(
    payload: CreateFolderRequest,
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> StorageFolder:
    try:
        folder = database.create_folder(user_id=user["id"], name=payload.name, parent_id=payload.parent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    folder["upload_count"] = 0
    return StorageFolder(**folder)


@app.post("/api/processing/configure", response_model=ProcessingConfigureResponse)
@app.post("/api/v1/processing/configure", response_model=ProcessingConfigureResponse)
def configure_processing(
    payload: ProcessingConfigureRequest,
    config: Annotated[Settings, Depends(app_settings)],
    user: Annotated[dict, Depends(current_user)],
) -> ProcessingConfigureResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Please enter an image configuration request.")
    suggestion, assistant_message = plan_processing_settings(payload.message, config)
    return ProcessingConfigureResponse(
        assistant_message=assistant_message,
        settings=ProcessingSettingsSuggestion(**suggestion),
    )


@app.post("/api/process", response_model=ProcessResponse)
@app.post("/api/v1/process", response_model=ProcessResponse)
async def process_image(
    file: Annotated[UploadFile, File()],
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
    style_id: Annotated[str, Form()] = "centerline",
    sensitivity: Annotated[float | None, Form()] = None,
    noise_filter: Annotated[int | None, Form()] = None,
    simplify_tolerance: Annotated[float | None, Form()] = None,
    mm_per_pixel: Annotated[float, Form()] = 1.0,
    slab_width_mm: Annotated[float | None, Form()] = None,
    slab_height_mm: Annotated[float | None, Form()] = None,
    folder_id: Annotated[str | None, Form()] = None,
) -> ProcessResponse:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Please upload an image file.")
    if len(image_bytes) > config.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Upload limit is {config.max_upload_mb} MB.")
    _ensure_storage_quota(
        config,
        additional_bytes=len(image_bytes) + JOB_STORAGE_RESERVE_BYTES,
        operation="image processing",
    )

    resolved_folder_id = _resolve_folder_id(database, user["id"], folder_id)
    upload_id, stored_path = _persist_upload(
        image_bytes=image_bytes,
        upload_dir=_folder_upload_dir(config.upload_dir, resolved_folder_id),
        original_filename=file.filename or "upload.image",
    )
    database.record_upload(
        upload_id=upload_id,
        folder_id=resolved_folder_id,
        original_filename=file.filename or "upload.image",
        stored_filename=stored_path.name,
        file_path=stored_path,
        content_type=file.content_type,
        user_id=user["id"],
    )

    request = ProcessingRequest(
        style_id=style_id,
        sensitivity=sensitivity,
        noise_filter=noise_filter,
        simplify_tolerance=simplify_tolerance,
        mm_per_pixel=mm_per_pixel,
        slab_width_mm=slab_width_mm,
        slab_height_mm=slab_height_mm,
        original_filename=file.filename or "upload.image",
    )

    try:
        manifest = await run_in_threadpool(
            process_upload,
            image_bytes=stored_path.read_bytes(),
            request=request,
            settings=config,
            segmenter=segmenter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    database.attach_upload_job(
        upload_id=upload_id,
        job_id=manifest.job_id,
        preview_path=manifest.preview_path,
        mask_path=manifest.mask_path,
        dxf_path=manifest.dxf_path,
    )

    return ProcessResponse(
        job_id=manifest.job_id,
        style_id=manifest.style_id,
        preview_url=f"/storage/jobs/{manifest.job_id}/preview.png",
        mask_url=f"/storage/jobs/{manifest.job_id}/mask.png",
        dxf_url=f"/api/v1/jobs/{manifest.job_id}/dxf",
        upload_id=upload_id,
        source_image_url=_storage_url(config.storage_dir, stored_path),
        metrics=manifest.metrics,
    )


@app.post("/api/process-sample", response_model=ProcessResponse)
@app.post("/api/v1/process-sample", response_model=ProcessResponse)
async def process_sample(
    config: Annotated[Settings, Depends(app_settings)],
    user: Annotated[dict, Depends(current_user)],
    sample_name: Annotated[str, Form()],
    style_id: Annotated[str, Form()] = "centerline",
    sensitivity: Annotated[float | None, Form()] = None,
    noise_filter: Annotated[int | None, Form()] = None,
    simplify_tolerance: Annotated[float | None, Form()] = None,
    mm_per_pixel: Annotated[float, Form()] = 1.0,
    slab_width_mm: Annotated[float | None, Form()] = None,
    slab_height_mm: Annotated[float | None, Form()] = None,
) -> ProcessResponse:
    sample_path = _resolve_sample_path(config.sample_dir, sample_name)
    if sample_path is None:
        raise HTTPException(status_code=404, detail="Sample image not found.")
    _ensure_storage_quota(
        config,
        additional_bytes=JOB_STORAGE_RESERVE_BYTES,
        operation="sample processing",
    )

    request = ProcessingRequest(
        style_id=style_id,
        sensitivity=sensitivity,
        noise_filter=noise_filter,
        simplify_tolerance=simplify_tolerance,
        mm_per_pixel=mm_per_pixel,
        slab_width_mm=slab_width_mm,
        slab_height_mm=slab_height_mm,
        original_filename=sample_path.name,
    )

    try:
        manifest = await run_in_threadpool(
            process_upload,
            image_bytes=sample_path.read_bytes(),
            request=request,
            settings=config,
            segmenter=segmenter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ProcessResponse(
        job_id=manifest.job_id,
        style_id=manifest.style_id,
        preview_url=f"/storage/jobs/{manifest.job_id}/preview.png",
        mask_url=f"/storage/jobs/{manifest.job_id}/mask.png",
        dxf_url=f"/api/v1/jobs/{manifest.job_id}/dxf",
        metrics=manifest.metrics,
    )


@app.get("/api/jobs/{job_id}", response_model=ProcessResponse)
@app.get("/api/v1/jobs/{job_id}", response_model=ProcessResponse)
def get_job(
    job_id: str,
    config: Annotated[Settings, Depends(app_settings)],
    user: Annotated[dict, Depends(current_user)],
) -> ProcessResponse:
    manifest = load_manifest(config, job_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return ProcessResponse(
        job_id=manifest.job_id,
        style_id=manifest.style_id,
        preview_url=f"/storage/jobs/{manifest.job_id}/preview.png",
        mask_url=f"/storage/jobs/{manifest.job_id}/mask.png",
        dxf_url=f"/api/v1/jobs/{manifest.job_id}/dxf",
        metrics=manifest.metrics,
    )


@app.get("/api/jobs/{job_id}/dxf")
@app.get("/api/v1/jobs/{job_id}/dxf")
def download_dxf(
    job_id: str,
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> FileResponse:
    manifest = load_manifest(config, job_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    latest_revision = database.latest_dxf_revision(job_id=job_id, user_id=user["id"])
    path = Path(latest_revision["dxf_path"]) if latest_revision else Path(manifest.dxf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="DXF output not found.")

    return FileResponse(
        path,
        media_type="application/dxf",
        filename=f"veincad-{job_id}.dxf",
    )


@app.post("/api/dxf/modify", response_model=DxfModifyResponse)
@app.post("/api/v1/dxf/modify", response_model=DxfModifyResponse)
async def modify_dxf(
    payload: DxfModifyRequest,
    config: Annotated[Settings, Depends(app_settings)],
    database: Annotated[Database, Depends(app_db)],
    user: Annotated[dict, Depends(current_user)],
) -> DxfModifyResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Please enter a CAD instruction.")

    manifest = load_manifest(config, payload.job_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    latest_revision = database.latest_dxf_revision(job_id=payload.job_id, user_id=user["id"])
    source_dxf = Path(latest_revision["dxf_path"]) if latest_revision else Path(manifest.dxf_path)
    if not source_dxf.exists():
        raise HTTPException(status_code=404, detail="DXF file not found.")
    _ensure_storage_quota(
        config,
        additional_bytes=DXF_REVISION_STORAGE_RESERVE_BYTES,
        operation="DXF revision",
    )

    actions, assistant_message = await run_in_threadpool(plan_dxf_actions, payload.message, config)
    database.record_dxf_message(job_id=payload.job_id, user_id=user["id"], role="user", content=payload.message)

    revision_id = uuid.uuid4().hex
    job_dir = config.storage_dir / "jobs" / payload.job_id
    if actions:
        dxf_path, preview_path, action_summary = await run_in_threadpool(
            apply_dxf_actions,
            source_dxf=source_dxf,
            job_dir=job_dir,
            revision_id=revision_id,
            actions=actions,
        )
        revision_url = f"/api/v1/jobs/{payload.job_id}/dxf"
        preview_url = f"/storage/jobs/{payload.job_id}/revisions/{revision_id}.png"
    else:
        dxf_path = source_dxf
        preview_path = None
        action_summary = "Clarification requested"
        revision_url = f"/api/v1/jobs/{payload.job_id}/dxf"
        preview_url = None

    database.record_dxf_message(
        job_id=payload.job_id,
        user_id=user["id"],
        role="assistant",
        content=f"{assistant_message} {action_summary}".strip(),
    )
    database.record_dxf_revision(
        revision_id=revision_id,
        job_id=payload.job_id,
        user_id=user["id"],
        prompt=payload.message,
        action_summary=action_summary,
        dxf_path=dxf_path,
        preview_path=preview_path,
    )

    messages = [
        DxfChatMessage(role=item["role"], content=item["content"], created_at=item["created_at"])
        for item in database.list_dxf_messages(job_id=payload.job_id, user_id=user["id"])
    ]
    return DxfModifyResponse(
        job_id=payload.job_id,
        revision_id=revision_id,
        assistant_message=f"{assistant_message} {action_summary}".strip(),
        dxf_url=revision_url,
        preview_url=preview_url,
        actions=actions,
        messages=messages,
    )


def _persist_upload(*, image_bytes: bytes, upload_dir: Path | None, original_filename: str) -> tuple[str, Path]:
    if upload_dir is None:
        raise HTTPException(status_code=500, detail="Upload storage is not configured.")
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}:
        suffix = ".image"
    upload_id = uuid.uuid4().hex
    stored_path = upload_dir / f"{upload_id}{suffix}"
    stored_path.write_bytes(image_bytes)
    return upload_id, stored_path


def _training_sample_response(record: dict) -> TrainingSampleResponse:
    sample_id = str(record["id"])
    return TrainingSampleResponse(
        **record,
        source_image_url=f"/api/v1/training/samples/{sample_id}/source",
        label_image_url=f"/api/v1/training/samples/{sample_id}/label",
    )


def _resolve_folder_id(database: Database, user_id: str, folder_id: str | None) -> str | None:
    if folder_id:
        folder = database.get_folder(folder_id=folder_id, user_id=user_id)
        if folder is None:
            raise HTTPException(status_code=404, detail="Storage folder not found.")
        return folder_id
    return database.default_folder_id(user_id=user_id)


def _folder_upload_dir(upload_dir: Path | None, folder_id: str | None) -> Path | None:
    if upload_dir is None:
        return None
    if not folder_id:
        return upload_dir
    return upload_dir / folder_id


def _storage_url(storage_dir: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(storage_dir.resolve())
    except ValueError:
        return ""
    return f"/storage/{relative.as_posix()}"


def _ensure_storage_quota(config: Settings, *, additional_bytes: int, operation: str) -> None:
    storage_bytes = _directory_size(config.storage_dir)
    projected_bytes = storage_bytes + max(additional_bytes, 0)
    if projected_bytes <= config.storage_quota_bytes:
        return
    available_bytes = max(config.storage_quota_bytes - storage_bytes, 0)
    raise HTTPException(
        status_code=413,
        detail=(
            f"Storage quota would be exceeded for {operation}. "
            f"Available: {_format_storage_bytes(available_bytes)}. "
            f"Quota: {_format_storage_bytes(config.storage_quota_bytes)}. "
            "Delete old uploads/jobs or raise VEINCAD_STORAGE_QUOTA_GB only if you accept possible storage charges."
        ),
    )


def _format_storage_bytes(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} GB"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} MB"
    if value >= 1_000:
        return f"{value / 1_000:.1f} KB"
    return f"{value} B"


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _job_count(storage_dir: Path) -> int:
    jobs_dir = storage_dir / "jobs"
    if not jobs_dir.exists():
        return 0
    return sum(1 for item in jobs_dir.iterdir() if item.is_dir())


def _resolve_sample_path(sample_dir: Path, sample_name: str) -> Path | None:
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    candidate = (sample_dir / Path(sample_name).name).resolve()
    sample_root = sample_dir.resolve()
    if sample_root not in candidate.parents:
        return None
    if candidate.suffix.lower() not in allowed_extensions:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate
