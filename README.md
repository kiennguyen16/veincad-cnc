# VeinCAD CNC

VeinCAD CNC is a full-stack prototype for turning stone vein imagery into CNC-friendly DXF linework.

It includes:

- A Next.js frontend for image upload, sample selection, style presets, preview, and DXF download.
- A FastAPI backend that runs an image-processing pipeline with OpenCV, scikit-image skeletonization, and ezdxf output.
- Secure login with a seeded admin account and HTTP-only session cookies.
- Persistent uploaded image storage and SQLite metadata tracking.
- A default 9.5 GB storage quota guard to stay below Cloudflare R2's 10 GB free storage allowance.
- Optional Cloudflare R2 object storage for hosted uploads, previews, training images, masks, and DXF files.
- A CAD chat workflow that creates revised DXF versions from natural-language edit requests.
- A chat-based image configuration workflow that can adjust extraction settings before DXF generation.
- An MCP server exposing the CAD and tracing tools for external AI agents.
- An optional SAM 2 integration point for segmentation model-assisted masking when you provide model dependencies and weights.

## Project Layout

```text
backend/   FastAPI API, processing pipeline, DXF generation
frontend/  Next.js app
sample_images/  Images extracted from the supplied attachment
```

## Run Locally

### Backend

```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\python -m pip install --upgrade pip
..\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

Open a second terminal:

```powershell
cd frontend
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

Then open http://localhost:3000.

Seed login:

```text
Email: slokermoliti@gmail.com
Password: Test123
```

## Deploy

The quickest hosted deployment path is Railway with two services. For larger uploaded files, enable Cloudflare R2 for object storage while keeping SQLite on the backend host. See `RAILWAY_DEPLOYMENT.md`.

## Optional SAM 2

The app runs without SAM 2. To enable it later, install the optional AI dependencies, provide a SAM 2 checkpoint/config or Hugging Face model name, and set `VEINCAD_ENABLE_SAM2=true` in `backend/.env`.

```powershell
cd backend
..\.venv\Scripts\python -m pip install -r requirements-ai.txt
```

SAM 2 model weights are intentionally not committed because they are large and environment-specific.

## Optional AI CAD Chat

The CAD chat has built-in local edits for common requests such as adding borders, smoothing lines, scaling, moving geometry, and tuning the OpenCV extraction settings. To let a hosted AI model translate broader natural-language requests, set Gemini or OpenAI credentials in `backend/.env`.

Recommended cheapest default for this use case:

```powershell
$env:GEMINI_API_KEY="your-key"
$env:VEINCAD_GEMINI_MODEL="gemini-2.5-flash-lite"
```

OpenAI fallback:

```powershell
$env:OPENAI_API_KEY="your-key"
$env:VEINCAD_OPENAI_MODEL="gpt-5.4-nano"
```

Gemini is tried first when `GEMINI_API_KEY` is present. OpenAI is tried second when `OPENAI_API_KEY` is present. If no key is configured, the app still handles common edits with deterministic local rules.

## MCP Server

Run the app's MCP server from the backend folder:

```powershell
cd backend
..\.venv\Scripts\python -m app.mcp_server
```

The server exposes these tools:

- `inspect_dxf` for entity counts, layers, and metrics.
- `add_border`, `smooth_geometry`, `move_geometry`, and `scale_geometry` for DXF revisions.
- `render_preview` for a PNG preview of a DXF job.
- `recommend_trace_settings` for natural-language OpenCV setting recommendations.

Use `mcp.client.example.json` as a starting point for MCP clients. Replace `GEMINI_API_KEY` with your key when you have it.

## Storage Repo

Uploaded slab images are saved under:

```text
backend/storage/uploads/slabs/{folder_id}/{upload_id}.{extension}
```

The SQLite database at `backend/storage/veincad.sqlite3` tracks each upload, its folder, original name, generated job, preview, mask, and DXF path. The UI lets you create folders, choose a destination folder before uploading, and browse/open stored uploads later.

For hosted file storage, set:

```text
VEINCAD_STORAGE_BACKEND=r2
VEINCAD_R2_ACCOUNT_ID=<cloudflare-account-id>
VEINCAD_R2_ACCESS_KEY_ID=<r2-access-key-id>
VEINCAD_R2_SECRET_ACCESS_KEY=<r2-secret-access-key>
VEINCAD_R2_BUCKET_NAME=veincad-storage
VEINCAD_R2_PREFIX=veincad
```

When R2 is enabled, uploads, generated previews, masks, training images, and DXF artifacts are mirrored to the bucket. SQLite still remains the app database for users, folders, sessions, and file metadata.

To avoid accidental Cloudflare R2 overage charges, the backend defaults to a 9.5 GB app storage quota:

```text
VEINCAD_STORAGE_QUOTA_GB=9.5
```

Uploads, training samples, sample processing, and DXF revisions are rejected before writing new files if they would push storage beyond the quota. Keep this value below `10` unless you intentionally accept possible storage charges.

## OpenCV Tuning

OpenCV is not directly fine-tuned like an AI model. Start by tuning `sensitivity`, `noise_filter`, and `simplify_tolerance`, then save presets per stone type. See `OPENCV_TUNING.md` for the calibration workflow and the later path to train U-Net, YOLO segmentation, or SAM/SAM 2 on labeled vein masks.

## CAD Notes

- DXF files use millimetres.
- The origin is the lower-left corner of the detected stone/work area.
- The UI defaults to a 3200 x 1600 mm slab scale. Change those fields before tracing when your real slab size differs.
- The default pipeline auto-detects a light stone slab when the image includes surrounding factory background.
- Bundled samples are served from `backend/data/samples` and can be processed through `/api/v1/process-sample`.

## Main API

- `GET /api/v1/health`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/styles`
- `GET /api/v1/samples`
- `GET /api/v1/uploads`
- `GET /api/v1/storage/folders`
- `POST /api/v1/storage/folders`
- `POST /api/v1/processing/configure` for chat-driven extraction setting changes
- `POST /api/v1/process` for user uploads
- `POST /api/v1/process-sample` for bundled samples
- `POST /api/v1/dxf/modify` for CAD chat revisions
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/dxf`
