# Railway Deployment Guide

This is the fastest path to host VeinCAD CNC away from the laptop while keeping costs controlled.

## Target Architecture

```text
Railway project
- backend service: FastAPI, OpenCV, DXF generation
- frontend service: Next.js
- backend volume: /app/storage for SQLite and local working files
- Cloudflare R2 bucket: uploads, previews, masks, training images, and DXF files
```

The first hosted version uses SQLite for users, folders, sessions, and metadata. Cloudflare R2 stores the larger file assets so your laptop does not need to stay awake and the app can stay under R2's 10 GB free allowance.

## 1. Create Railway Project

1. Sign in to Railway.
2. Create a new empty project.
3. Connect GitHub repo:

```text
https://github.com/kiennguyen16/veincad-cnc
```

## 2. Backend Service

Create a service named `veincad-backend`.

Set:

```text
Root Directory: /backend
Config File Path: /backend/railway.toml
```

Generate a public Railway domain for the backend. Copy it; it will look similar to:

```text
https://veincad-backend-production.up.railway.app
```

Add a small persistent volume for SQLite:

```text
Mount Path: /app/storage
```

Backend variables:

```text
VEINCAD_CORS_ORIGINS=https://YOUR_FRONTEND_DOMAIN
VEINCAD_AUTH_COOKIE_SECURE=true
VEINCAD_SEED_ADMIN_EMAIL=slokermoliti@gmail.com
VEINCAD_SEED_ADMIN_PASSWORD=CHANGE_THIS_TEMP_PASSWORD
VEINCAD_MAX_UPLOAD_MB=25
VEINCAD_STORAGE_QUOTA_GB=9.5
VEINCAD_STORAGE_BACKEND=r2
VEINCAD_R2_ACCOUNT_ID=YOUR_CLOUDFLARE_ACCOUNT_ID
VEINCAD_R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
VEINCAD_R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
VEINCAD_R2_BUCKET_NAME=veincad-storage
VEINCAD_R2_PREFIX=veincad
VEINCAD_ENABLE_SAM2=false
VEINCAD_FRONTEND_URL=https://YOUR_FRONTEND_DOMAIN
```

If you want a no-R2 test deployment first, set `VEINCAD_STORAGE_BACKEND=local` and lower `VEINCAD_STORAGE_QUOTA_GB` to the size of your backend volume, for example `0.45`.

Optional AI variables:

```text
GEMINI_API_KEY=
VEINCAD_GEMINI_MODEL=gemini-2.5-flash-lite
OPENAI_API_KEY=
VEINCAD_OPENAI_MODEL=gpt-5.4-nano
```

## 3. Frontend Service

Create a service named `veincad-frontend`.

Set:

```text
Root Directory: /frontend
Config File Path: /frontend/railway.toml
```

Generate a public Railway domain for the frontend. Copy it; it will look similar to:

```text
https://veincad-frontend-production.up.railway.app
```

Frontend variables:

```text
NEXT_PUBLIC_API_BASE_URL=
API_PROXY_TARGET=https://YOUR_BACKEND_DOMAIN
```

Keep `NEXT_PUBLIC_API_BASE_URL` blank so the browser calls `/api`, `/storage`, and `/sample_images` on the frontend domain. The Next.js service proxies those requests to the backend. This keeps login cookies same-origin.

## 4. Update Cross-Service URLs

After both domains exist:

1. Set backend `VEINCAD_CORS_ORIGINS` to the frontend domain.
2. Set backend `VEINCAD_FRONTEND_URL` to the frontend domain.
3. Set frontend `API_PROXY_TARGET` to the backend domain.
4. Redeploy both services.

## 5. First Login

Open the frontend domain and sign in with:

```text
Email: slokermoliti@gmail.com
Password: the value you set in VEINCAD_SEED_ADMIN_PASSWORD
```

Change the admin password after first login.

## 6. Verify

Check:

- Login works.
- Admin page opens only for `slokermoliti@gmail.com`.
- Storage card shows used space and quota.
- Sample images load.
- Uploading an image persists it in Storage Repo.
- Trace Image produces a preview and DXF download.
- Restart/redeploy the backend and confirm uploads still exist.

## Cost Guard

The backend enforces `VEINCAD_STORAGE_QUOTA_GB` before accepting new uploads, training data, sample jobs, and DXF revisions.

Recommended values:

```text
Small Railway test volume: 0.45
Cloudflare R2 free tier: 9.5
```

Do not set the quota above the free storage allowance unless you accept possible overage charges.
