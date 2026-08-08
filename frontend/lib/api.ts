export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";

export type StylePreset = {
  id: string;
  name: string;
  summary: string;
  output_mode: string;
  default_sensitivity: number;
  default_noise_filter: number;
  default_simplify_tolerance: number;
};

export type SampleImage = {
  name: string;
  url: string;
  width?: number | null;
  height?: number | null;
};

export type StorageFolder = {
  id: string;
  name: string;
  parent_id?: string | null;
  owner_user_id: string;
  created_at: string;
  upload_count: number;
};

export type UploadRecord = {
  id: string;
  folder_id?: string | null;
  folder_name?: string | null;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  upload_timestamp: string;
  associated_user_id: string;
  generated_job_id?: string | null;
  preview_path?: string | null;
  mask_path?: string | null;
  dxf_path?: string | null;
  source_image_url?: string | null;
};

export type ProcessMetrics = {
  width_px: number;
  height_px: number;
  work_area: number[];
  mm_per_pixel: number;
  scale_confirmed: boolean;
  line_count: number;
  total_length_mm: number;
  used_sam2: boolean;
  processing_ms: number;
};

export type ProcessResponse = {
  job_id: string;
  style_id: string;
  preview_url: string;
  mask_url: string;
  dxf_url: string;
  upload_id?: string | null;
  source_image_url?: string | null;
  metrics: ProcessMetrics;
};

export type HealthResponse = {
  ok: boolean;
  sam2_available: boolean;
};

export type ProcessSettings = {
  styleId: string;
  sensitivity: number;
  noiseFilter: number;
  simplifyTolerance: number;
  slabWidthMm: number;
  slabHeightMm: number;
};

export type User = {
  id: string;
  email: string;
  role: string;
};

export type AuthResponse = {
  user: User;
};

export type MessageResponse = {
  ok: boolean;
  message: string;
};

export type AdminLatestUpload = {
  id: string;
  original_filename: string;
  folder_name?: string | null;
  upload_timestamp: string;
  associated_user_id: string;
  user_email: string;
  generated_job_id?: string | null;
};

export type AdminSummary = {
  admin_email: string;
  user_count: number;
  active_session_count: number;
  upload_count: number;
  folder_count: number;
  dxf_revision_count: number;
  dxf_message_count: number;
  job_count: number;
  storage_bytes: number;
  storage_quota_bytes: number;
  storage_available_bytes: number;
  storage_usage_percent: number;
  storage_path: string;
  latest_uploads: AdminLatestUpload[];
};

export type DxfChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string | null;
};

export type DxfModifyResponse = {
  job_id: string;
  revision_id: string;
  assistant_message: string;
  dxf_url: string;
  preview_url?: string | null;
  actions: Record<string, unknown>[];
  messages: DxfChatMessage[];
};

export type ProcessingConfigureResponse = {
  assistant_message: string;
  settings: {
    style_id: string;
    sensitivity: number;
    noise_filter: number;
    simplify_tolerance: number;
  };
};

export type TrainingStyleId = "centerline" | "high_detail";

export type TrainingSample = {
  id: string;
  style_id: TrainingStyleId;
  source_original_filename: string;
  label_original_filename: string;
  source_image_url: string;
  label_image_url: string;
  notes?: string | null;
  status: string;
  created_at: string;
  created_by: string;
};

export type TrainingSummary = {
  total_samples: number;
  counts_by_style: Record<TrainingStyleId, number>;
  required_per_style: number;
  ready_to_train: boolean;
  status: string;
};

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
    if (typeof body?.error?.message === "string") {
      return body.error.message;
    }
  } catch {
    // Fall back to status text below.
  }
  return response.statusText || "Request failed";
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(apiUrl("/api/v1/health"), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const response = await fetch(apiUrl("/api/v1/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function requestPasswordReset(email: string): Promise<MessageResponse> {
  const response = await fetch(apiUrl("/api/v1/auth/forgot-password"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function resetPassword(token: string, password: string): Promise<MessageResponse> {
  const response = await fetch(apiUrl("/api/v1/auth/reset-password"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function logout(): Promise<void> {
  const response = await fetch(apiUrl("/api/v1/auth/logout"), {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function getMe(): Promise<AuthResponse> {
  const response = await fetch(apiUrl("/api/v1/auth/me"), {
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function getAdminSummary(): Promise<AdminSummary> {
  const response = await fetch(apiUrl("/api/v1/admin/summary"), {
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function createAdminUser(email: string, password: string): Promise<User> {
  const response = await fetch(apiUrl("/api/v1/admin/users"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function getTrainingSamples(): Promise<TrainingSample[]> {
  const response = await fetch(apiUrl("/api/v1/training/samples"), {
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function getTrainingSummary(): Promise<TrainingSummary> {
  const response = await fetch(apiUrl("/api/v1/training/summary"), {
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function createTrainingSample(
  sourceImage: File,
  labelImage: File,
  styleId: TrainingStyleId,
  notes: string,
): Promise<TrainingSample> {
  const body = new FormData();
  body.append("source_image", sourceImage);
  body.append("label_image", labelImage);
  body.append("style_id", styleId);
  if (notes.trim()) {
    body.append("notes", notes.trim());
  }

  const response = await fetch(apiUrl("/api/v1/training/samples"), {
    method: "POST",
    credentials: "include",
    body,
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function deleteTrainingSample(sampleId: string): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/training/samples/${encodeURIComponent(sampleId)}`), {
    method: "DELETE",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function getStyles(): Promise<StylePreset[]> {
  const response = await fetch(apiUrl("/api/v1/styles"), { cache: "no-store", credentials: "include" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function getSamples(): Promise<SampleImage[]> {
  const response = await fetch(apiUrl("/api/v1/samples"), { cache: "no-store", credentials: "include" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function getJob(jobId: string): Promise<ProcessResponse> {
  const response = await fetch(apiUrl(`/api/v1/jobs/${jobId}`), { cache: "no-store", credentials: "include" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

function appendSettings(body: FormData, settings: ProcessSettings) {
  body.append("style_id", settings.styleId);
  body.append("sensitivity", String(settings.sensitivity));
  body.append("noise_filter", String(settings.noiseFilter));
  body.append("simplify_tolerance", String(settings.simplifyTolerance));

  if (settings.slabWidthMm > 0) {
    body.append("slab_width_mm", String(settings.slabWidthMm));
  }
  if (settings.slabHeightMm > 0) {
    body.append("slab_height_mm", String(settings.slabHeightMm));
  }
  if (settings.slabWidthMm <= 0 && settings.slabHeightMm <= 0) {
    body.append("mm_per_pixel", "1");
  }
}

export async function getFolders(): Promise<StorageFolder[]> {
  const response = await fetch(apiUrl("/api/v1/storage/folders"), {
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function createFolder(name: string): Promise<StorageFolder> {
  const response = await fetch(apiUrl("/api/v1/storage/folders"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function getUploads(folderId?: string | null): Promise<UploadRecord[]> {
  const suffix = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : "";
  const response = await fetch(apiUrl(`/api/v1/uploads${suffix}`), {
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function processImage(
  file: File,
  settings: ProcessSettings,
  folderId?: string | null,
): Promise<ProcessResponse> {
  const body = new FormData();
  body.append("file", file);
  appendSettings(body, settings);
  if (folderId) {
    body.append("folder_id", folderId);
  }

  const response = await fetch(apiUrl("/api/v1/process"), {
    method: "POST",
    credentials: "include",
    body,
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}

export async function processSample(sampleName: string, settings: ProcessSettings): Promise<ProcessResponse> {
  const body = new FormData();
  body.append("sample_name", sampleName);
  appendSettings(body, settings);

  const response = await fetch(apiUrl("/api/v1/process-sample"), {
    method: "POST",
    credentials: "include",
    body,
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}

export async function configureProcessing(message: string): Promise<ProcessingConfigureResponse> {
  const response = await fetch(apiUrl("/api/v1/processing/configure"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}

export async function modifyDxf(jobId: string, message: string): Promise<DxfModifyResponse> {
  const response = await fetch(apiUrl("/api/v1/dxf/modify"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ job_id: jobId, message }),
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}
