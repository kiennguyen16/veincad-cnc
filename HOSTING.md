# Hosting & Domain Guide

## Current Recommended Plan

Use **Vercel for the frontend** and **Render Free Web Service for the backend** unless you subscribe to Hugging Face PRO.

The exact free checklist is in `VERCEL_RENDER_DEPLOYMENT.md`.

Hugging Face Docker Spaces are supported by this repo, but Hugging Face currently requires PRO for personal accounts to create Docker/Gradio compute Spaces. See `VERCEL_HUGGINGFACE_DEPLOYMENT.md` only if you choose Hugging Face PRO.

Important:

- Vercel project root directory: `frontend`
- Render backend root directory: `backend`
- Render backend runtime: `Docker`
- Frontend env: `API_PROXY_TARGET=https://veincad-cnc.onrender.com`
- Keep `NEXT_PUBLIC_API_BASE_URL` blank so login cookies work through the Vercel proxy.

## Free Temporary Public Demo

Cloudflare Quick Tunnel can expose the complete local application through one
temporary HTTPS URL without opening router ports or creating a Cloudflare
account. VeinCAD's Next.js service proxies `/api/*` and `/storage/*` to the
local FastAPI service, so authentication cookies, uploads, previews, and DXF
downloads all use the same public origin.

Start the backend and frontend, then run:

```powershell
cloudflared tunnel --url http://127.0.0.1:3000 --no-autoupdate
```

Cloudflare prints a random `https://...trycloudflare.com` address. This option
is for testing only: the URL changes after restart, the computer must remain
awake and online, there is no uptime guarantee, and Quick Tunnels are limited
to 200 concurrent in-flight requests.

Before sharing a tunnel beyond trusted testers, replace the seeded `Test123`
administrator password with a strong unique password.

For a stable domain while still running the application on this computer,
create a free Cloudflare account, add the domain to Cloudflare DNS, create a
named Tunnel, and map `app.yourdomain.com` to `http://127.0.0.1:3000`.

## Recommended Low-Cost Setup

Use a host that supports a persistent Python backend because this app processes images, stores uploads, generates DXF files, and may call an AI model.

For the first hosted version, use Railway with two services and a persistent backend volume. The exact checklist is in `RAILWAY_DEPLOYMENT.md`.

Good options:

| Provider | Fit | Notes |
| :--- | :--- | :--- |
| Render | Simple full-stack deployment | Free or low-cost services. Free services may sleep after inactivity. |
| Railway | Container-friendly deployment | Good for Docker and persistent volumes. Usage-based pricing. |
| Hugging Face Spaces | ML/demo deployment | Useful for image-processing demos. Public/private and secret settings need care. |

For production, configure:

- Frontend: Next.js service.
- Backend: FastAPI service.
- Persistent storage: small mounted disk/volume for SQLite plus Cloudflare R2 for uploads, previews, masks, training images, and DXF files.
- Database: SQLite on the persistent volume for small deployments, or Postgres for larger/multi-user deployments.
- Storage budget: keep `VEINCAD_STORAGE_QUOTA_GB=9.5` so app data stays below Cloudflare R2's 10 GB free storage allowance.

## Required Environment Variables

Frontend:

```text
# Recommended single-origin deployment
NEXT_PUBLIC_API_BASE_URL=
API_PROXY_TARGET=http://127.0.0.1:8000
```

Backend:

```text
VEINCAD_CORS_ORIGINS=https://app.yourdomain.com
VEINCAD_AUTH_COOKIE_SECURE=true
VEINCAD_SEED_ADMIN_EMAIL=slokermoliti@gmail.com
VEINCAD_SEED_ADMIN_PASSWORD=<change-this-after-first-login>
VEINCAD_MAX_UPLOAD_MB=25
VEINCAD_STORAGE_QUOTA_GB=9.5
VEINCAD_STORAGE_BACKEND=r2
VEINCAD_R2_ACCOUNT_ID=<your-cloudflare-account-id>
VEINCAD_R2_ACCESS_KEY_ID=<your-r2-access-key-id>
VEINCAD_R2_SECRET_ACCESS_KEY=<your-r2-secret-access-key>
VEINCAD_R2_BUCKET_NAME=veincad-storage
VEINCAD_R2_PREFIX=veincad
VEINCAD_ENABLE_SAM2=false
```

Optional AI CAD chat:

```text
GEMINI_API_KEY=<your-gemini-api-key>
VEINCAD_GEMINI_MODEL=gemini-2.5-flash-lite

# Optional OpenAI fallback
OPENAI_API_KEY=<your-openai-api-key>
VEINCAD_OPENAI_MODEL=gpt-5.4-nano
```

For the CAD/chat workload, Gemini 2.5 Flash-Lite is the lowest-cost default configured in the app. The backend also works without an API key for simple deterministic edits.

## Domain DNS Records

Do not guess the final target. Add the custom domain inside your hosting provider first, then copy the exact DNS value it gives you.

### Recommended Subdomain Setup

Use two subdomains:

```text
app.yourdomain.com -> frontend
api.yourdomain.com -> backend
```

Typical DNS records:

```text
Type:  CNAME
Name:  app
Value: your-frontend-host.onrender.com
TTL:   Auto
```

```text
Type:  CNAME
Name:  api
Value: your-backend-host.onrender.com
TTL:   Auto
```

Then set:

```text
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com
VEINCAD_CORS_ORIGINS=https://app.yourdomain.com
```

### Root Domain Setup

If you want `yourdomain.com` instead of `app.yourdomain.com`, follow the host's custom domain panel.

If the host gives a static IP:

```text
Type:  A
Name:  @
Value: 123.45.67.89
TTL:   Auto
```

If the host gives a CNAME-like target for root/apex, use your DNS provider's `ALIAS`, `ANAME`, or flattened CNAME feature if available.

## Free Hosting Note

Free tiers are useful for testing, but image uploads and generated DXF files require persistence. If the host does not include persistent disks on the free tier, use external object storage such as Supabase Storage, S3, or Cloudflare R2 before trusting it with real customer work.

Cloudflare R2 may show `$0/month` but still require a card because overage rates apply after the included allowance. Keep the app quota below the free 10 GB allowance:

```text
VEINCAD_STORAGE_QUOTA_GB=9.5
```

The backend enforces this cap before accepting uploads, training images, sample jobs, or DXF revisions. The admin page shows used storage, quota, percent used, and remaining free space.
