# Vercel Frontend + Render Backend Deployment

This is the lowest-friction free showcase path for VeinCAD CNC now that Hugging Face requires PRO for Docker/compute Spaces.

- **Frontend:** Vercel Hobby, deployed from the `frontend` directory.
- **Backend:** Render Free Web Service, deployed from `backend/Dockerfile`.
- **File storage:** Cloudflare R2, capped by `VEINCAD_STORAGE_QUOTA_GB=9.5`.
- **Database:** SQLite on the backend container for demo users and metadata. Render free services have ephemeral disk, so move the database to Postgres later if you need durable user records.

## 1. Backend On Render

Use the existing Render backend service if it is already live:

```text
https://veincad-cnc.onrender.com
```

Backend health check:

```text
https://veincad-cnc.onrender.com/api/v1/health
```

Expected:

```json
{"ok": true, "sam2_available": false}
```

If creating a new Render backend:

1. Go to [Render New Web Service](https://dashboard.render.com/select-repo?type=web).
2. Connect the GitHub repo.
3. Runtime: `Docker`.
4. Root directory: `backend`.
5. Dockerfile path: leave default or use `./Dockerfile`.
6. Instance type: `Free`.

## 2. Backend Environment Variables

In Render backend -> **Environment**, set:

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

## 3. Frontend On Vercel

1. Go to [Vercel New Project](https://vercel.com/new).
2. Import the GitHub repo.
3. Set **Root Directory** to:

```text
frontend
```

4. Keep framework as **Next.js**.
5. Add this environment variable:

```ini
API_PROXY_TARGET=https://veincad-cnc.onrender.com
```

6. Do **not** set `NEXT_PUBLIC_API_BASE_URL`. Leave it blank or delete it.
7. Deploy.

## 4. Why The Proxy Matters

The browser should call:

```text
https://<your-vercel-app>.vercel.app/api/v1/auth/login
```

Vercel then proxies that request to:

```text
https://veincad-cnc.onrender.com/api/v1/auth/login
```

Do not make the browser call the backend directly with `NEXT_PUBLIC_API_BASE_URL`, because split frontend/backend domains can break login cookies.

## 5. Free-Tier Caveats

Render free backend services spin down after inactivity and may take about a minute to wake up. Render free services also have ephemeral local files, so Cloudflare R2 is required for uploaded images and generated outputs.

Keep:

```ini
VEINCAD_STORAGE_QUOTA_GB=9.5
```

This keeps app-managed object storage below Cloudflare R2's 10 GB free allowance.
