# Vercel Frontend + Hugging Face Backend Deployment

This is the recommended low-cost showcase deployment for VeinCAD CNC:

- **Frontend:** Vercel, deployed from the `frontend` directory.
- **Backend:** Hugging Face Spaces, Docker SDK, deployed from the repository root `Dockerfile`.
- **File storage:** Cloudflare R2, capped by `VEINCAD_STORAGE_QUOTA_GB=9.5`.
- **Database:** SQLite inside the backend container for the demo account and metadata. For durable production users, move this to Postgres later.

## 1. Deploy Backend To Hugging Face Spaces

1. Go to [Hugging Face Spaces](https://huggingface.co/spaces).
2. Click **Create new Space**.
3. Choose:
   - **Space name:** `veincad-cnc` or similar
   - **SDK:** `Docker`
   - **Hardware:** Free CPU for showcase testing
   - **Visibility:** Private while testing, Public only when you are ready
4. Upload or connect this repository so the Space can build from the root `Dockerfile`.
5. The backend must listen on port `7860`; the root `Dockerfile` already does this.

After deploy, your backend URL will look like:

```text
https://<your-hf-username>-veincad-cnc.hf.space
```

Check:

```text
https://<your-hf-username>-veincad-cnc.hf.space/api/v1/health
```

Expected:

```json
{"ok": true, "sam2_available": false}
```

## 2. Hugging Face Backend Secrets

In the Space, go to **Settings** -> **Variables and secrets**.

Add these as secrets or variables:

```ini
VEINCAD_CORS_ORIGINS=https://<your-vercel-app>.vercel.app
VEINCAD_FRONTEND_URL=https://<your-vercel-app>.vercel.app
VEINCAD_AUTH_COOKIE_SECURE=true
VEINCAD_SEED_ADMIN_EMAIL=slokermoliti@gmail.com
VEINCAD_SEED_ADMIN_PASSWORD=<your-admin-password>
VEINCAD_MAX_UPLOAD_MB=25
VEINCAD_STORAGE_BACKEND=r2
VEINCAD_STORAGE_QUOTA_GB=9.5
VEINCAD_R2_ACCOUNT_ID=<your-cloudflare-account-id>
VEINCAD_R2_ACCESS_KEY_ID=<your-r2-access-key-id>
VEINCAD_R2_SECRET_ACCESS_KEY=<your-r2-secret-access-key>
VEINCAD_R2_BUCKET_NAME=veincad-storage
VEINCAD_R2_PREFIX=veincad
VEINCAD_ENABLE_SAM2=false
```

Optional AI CAD chat:

```ini
GEMINI_API_KEY=<your-gemini-api-key>
VEINCAD_GEMINI_MODEL=gemini-2.5-flash-lite

# Optional OpenAI fallback
OPENAI_API_KEY=<your-openai-api-key>
VEINCAD_OPENAI_MODEL=gpt-5.4-nano
```

## 3. Deploy Frontend To Vercel

1. Go to [Vercel New Project](https://vercel.com/new).
2. Import the GitHub repository.
3. Set **Root Directory** to:

```text
frontend
```

4. Keep framework as **Next.js**.
5. Add this environment variable:

```ini
API_PROXY_TARGET=https://<your-hf-username>-veincad-cnc.hf.space
```

6. Do **not** set `NEXT_PUBLIC_API_BASE_URL` for the Vercel production app. Leave it blank or delete it.
7. Deploy.

## 4. Why `NEXT_PUBLIC_API_BASE_URL` Should Stay Blank

For login to work reliably, the browser should call:

```text
https://<your-vercel-app>.vercel.app/api/v1/auth/login
```

Vercel then rewrites `/api/*` internally to Hugging Face:

```text
https://<your-hf-username>-veincad-cnc.hf.space/api/*
```

This keeps browser requests on one frontend origin and avoids cross-site login cookie problems.

Do not set:

```ini
NEXT_PUBLIC_API_BASE_URL=https://<your-hf-username>-veincad-cnc.hf.space
```

That makes the browser call Hugging Face directly and can break authentication.

## 5. After Vercel Deploys

Update the Hugging Face backend variables with your final Vercel URL:

```ini
VEINCAD_CORS_ORIGINS=https://<your-vercel-app>.vercel.app
VEINCAD_FRONTEND_URL=https://<your-vercel-app>.vercel.app
```

Restart or rebuild the Hugging Face Space after changing backend variables.

## 6. Storage Limit

Cloudflare R2 includes 10 GB/month storage on the free allowance, but overages can be billed. Keep:

```ini
VEINCAD_STORAGE_QUOTA_GB=9.5
```

The backend checks this before accepting uploads, training images, generated masks, previews, DXF files, and DXF revisions.

## 7. Current Repo Deployment Files

- `frontend/vercel.json`: Vercel frontend project config.
- `frontend/next.config.ts`: proxies `/api/*`, `/storage/*`, and `/sample_images/*` to the backend using `API_PROXY_TARGET`.
- `Dockerfile`: Hugging Face backend Docker image, listening on port `7860`.
- `.dockerignore`: keeps personal docs, local storage, frontend builds, and development artifacts out of the backend Docker build context.

