from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=24, max_length=256)
    password: str = Field(..., min_length=6, max_length=128)


class MessageResponse(BaseModel):
    ok: bool
    message: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str


class AuthResponse(BaseModel):
    user: UserResponse


class AdminLatestUpload(BaseModel):
    id: str
    original_filename: str
    folder_name: str | None = None
    upload_timestamp: str
    associated_user_id: str
    user_email: str
    generated_job_id: str | None = None


class AdminSummary(BaseModel):
    admin_email: str
    user_count: int
    active_session_count: int
    upload_count: int
    folder_count: int
    dxf_revision_count: int
    dxf_message_count: int
    job_count: int
    storage_bytes: int
    storage_path: str
    latest_uploads: list[AdminLatestUpload]


class AdminCreateUserRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=6, max_length=128)


class TrainingSampleResponse(BaseModel):
    id: str
    style_id: str
    source_original_filename: str
    label_original_filename: str
    source_image_url: str
    label_image_url: str
    notes: str | None = None
    status: str
    created_at: str
    created_by: str


class TrainingSummaryResponse(BaseModel):
    total_samples: int
    counts_by_style: dict[str, int]
    required_per_style: int
    ready_to_train: bool
    status: str


class StyleResponse(BaseModel):
    id: str
    name: str
    summary: str
    output_mode: str
    default_sensitivity: float
    default_noise_filter: int
    default_simplify_tolerance: float


class SampleImage(BaseModel):
    name: str
    url: str
    width: int | None = None
    height: int | None = None


class UploadRecord(BaseModel):
    id: str
    folder_id: str | None = None
    folder_name: str | None = None
    original_filename: str
    stored_filename: str
    file_path: str
    upload_timestamp: str
    associated_user_id: str
    generated_job_id: str | None = None
    preview_path: str | None = None
    mask_path: str | None = None
    dxf_path: str | None = None
    source_image_url: str | None = None


class StorageFolder(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    owner_user_id: str
    created_at: str
    upload_count: int = 0


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: str | None = None


class ProcessMetrics(BaseModel):
    width_px: int
    height_px: int
    work_area: list[int]
    mm_per_pixel: float
    scale_confirmed: bool
    line_count: int
    total_length_mm: float
    used_sam2: bool
    processing_ms: int


class ProcessResponse(BaseModel):
    job_id: str
    style_id: str
    preview_url: str
    mask_url: str
    dxf_url: str
    upload_id: str | None = None
    source_image_url: str | None = None
    metrics: ProcessMetrics


class ProcessingSettingsSuggestion(BaseModel):
    style_id: str
    sensitivity: float
    noise_filter: int
    simplify_tolerance: float


class ProcessingConfigureRequest(BaseModel):
    message: str


class ProcessingConfigureResponse(BaseModel):
    assistant_message: str
    settings: ProcessingSettingsSuggestion


class JobManifest(BaseModel):
    job_id: str
    style_id: str
    original_filename: str
    preview_path: str
    mask_path: str
    dxf_path: str
    metrics: ProcessMetrics


class DxfChatMessage(BaseModel):
    role: str
    content: str
    created_at: str | None = None


class DxfModifyRequest(BaseModel):
    job_id: str
    message: str


class DxfModifyResponse(BaseModel):
    job_id: str
    revision_id: str
    assistant_message: str
    dxf_url: str
    preview_url: str | None = None
    actions: list[dict] = Field(default_factory=list)
    messages: list[DxfChatMessage] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str = Field(..., examples=["The uploaded file is not a readable image."])
