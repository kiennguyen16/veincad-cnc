# Codex Implementation Specification & Hosting Guide

This document outlines the detailed prompts, functional specifications, and deployment configurations for the CNC Slab Tile Vein Extraction Application.

---

## 1. Codex Functional Prompts

To implement the required changes effectively, provide the following prompts to Codex sequentially based on your architectural layer.

### Requirement 1: Authentication & Seed Account

**Prompt for Codex:**

```text
Modify the application to implement secure user authentication.

1. Frontend:
   - Create a responsive login page with input validation for email and password.
   - After successful login, route the user into the main CNC vein extraction workspace.
   - Add logout support and preserve authenticated state across page refreshes.

2. Backend:
   - Implement JWT-based authentication or secure HTTP-only session cookies.
   - Protect all core API routes, including image upload, DXF processing, saved jobs, and CAD chat, so they require a valid session.
   - Return consistent 401/403 responses for unauthenticated or unauthorized requests.

3. Database Seeding:
   - Create a backend initialization script that checks for an existing user and seeds a default administrator account only if it does not already exist.
   - Use a secure password hashing library, such as bcrypt or passlib[bcrypt], to hash the seed password before saving it.
   - Do not hardcode or store the plain text password in the database.

Default seed account:
- Email: slokermoliti@gmail.com
- Password: Test123
```

> Security note: keep the seed password in an environment variable for real deployments, then change it immediately after first login.

### Requirement 2: Image Persistence & Storage Location

**Prompt for Codex:**

```text
Update the core image upload module to ensure uploaded slab tile images are properly persisted on the server.

1. Storage Strategy:
   - Create a local storage manager that writes incoming images to a dedicated directory, such as ./storage/uploads/slabs/.
   - Ensure the application checks for and creates this directory structure on startup.
   - Keep generated previews, masks, and DXF outputs in related job folders so each upload can be traced to its output files.

2. File Handling:
   - Generate a unique cryptographic filename, such as UUIDv4 plus the original extension, upon file receipt to prevent naming collisions.
   - Preserve the original filename in metadata only; never trust it as a storage path.
   - Validate supported image types and maximum file size before saving.

3. Database Tracking:
   - Save a metadata entry for every upload into the database.
   - Track these fields at minimum:
     - id
     - original_filename
     - stored_filename
     - file_path
     - upload_timestamp
     - associated_user_id
     - generated_job_id
     - preview_path
     - mask_path
     - dxf_path
```

### Requirement 3: Iterative DXF Modification via AI Chat

**Prompt for Codex:**

```text
Implement a conversational CAD workflow enabling users to iteratively adjust the generated DXF vector data using an LLM.

1. Frontend Layout:
   - Split the workspace screen.
   - Keep the primary DXF preview canvas on one side.
   - Embed an interactive chat window component on the other side.
   - Show a history of CAD changes and allow downloading the latest revised DXF version.

2. Backend Endpoint:
   - Expose a POST route /api/dxf/modify.
   - The route should accept:
     - current DXF file identifier or job ID
     - user text prompt
     - optional target layer/entity hints
   - Example user prompts:
     - "smooth out the primary vein line"
     - "offset the secondary vein by 5mm"
     - "add a 10mm border around the slab"

3. LLM Orchestration:
   - Construct a backend service that sends the user's natural language request to an LLM.
   - Use a strict system prompt that forces structured JSON output.
   - The JSON schema should describe vector transformations, such as:
     - command type
     - target layer
     - target entity IDs
     - coordinates
     - scale factors
     - offsets
     - smoothing tolerance
     - new entities to add
   - Reject or ask for clarification when the instruction is too vague or unsafe for CNC output.

4. DXF Rewriter:
   - Write a utility using a DXF parsing library, such as ezdxf, that accepts the structured modifications.
   - Read the existing DXF file.
   - Apply the requested vector edits.
   - Save a new version of the DXF file without overwriting the original.
   - Return the updated preview data, metrics, and download URL to the frontend.
```

---

## 2. Infrastructure & Hosting Guide

For applications handling raw image uploads and streaming AI vector transformations, selecting a platform that supports persistent backend environments is crucial.

### Free & Low-Cost Deployment Options

| Provider | Type | Estimated Cost | Pros / Cons |
| :--- | :--- | :--- | :--- |
| **Render.com** | Web Service | Free tier or low-cost paid plans | **Pros:** Native support for Node.js/Python, automatic TLS, simple deployment flow.<br>**Cons:** Free tier services may spin down after inactivity, causing cold-start delays. |
| **Railway.app** | Container / App Platform | Low-cost usage-based plans | **Pros:** Good full-stack and Docker support, strong developer experience, persistent volume options.<br>**Cons:** Free/trial credits are limited. |
| **Hugging Face Spaces** | Docker App | Free tier available | **Pros:** Good for ML-heavy demos and image-processing utilities.<br>**Cons:** Public app defaults and environment variable handling need careful setup. |

### Recommended Deployment Shape

For this application, use a platform that can run both:

- A persistent Python FastAPI backend for image processing, DXF generation, storage, and AI/CAD chat.
- A Next.js frontend connected to the backend through environment variables.

Best practical options:

1. **Render or Railway with Docker Compose-style services**
   - Frontend service: Next.js app.
   - Backend service: FastAPI app.
   - Persistent disk/volume: image uploads and generated DXF files.

2. **Separate frontend and backend hosting**
   - Frontend: Vercel or Netlify.
   - Backend: Render, Railway, Fly.io, or another Python-friendly host.
   - Storage: persistent backend volume, S3-compatible storage, Supabase Storage, or Cloudflare R2.

### Environment Variables To Configure

```text
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com

VEINCAD_CORS_ORIGINS=https://app.yourdomain.com
VEINCAD_ENABLE_SAM2=false
VEINCAD_MAX_UPLOAD_MB=25

AUTH_SECRET=<strong-random-secret>
SEED_ADMIN_EMAIL=slokermoliti@gmail.com
SEED_ADMIN_PASSWORD=Test123

OPENAI_API_KEY=<only required for AI CAD chat>
```

---

## 3. Custom Domain Configuration

After registering your domain through your domain manager, such as Cloudflare, Namecheap, or GoDaddy, complete your setup using one of the routing options below depending on where you want the app hosted.

### Option 1: Configuring a Subdomain

If your primary app should live at a subdomain like `app.yourdomain.com` or `cnc.yourdomain.com`, set up a **CNAME** record.

| Field | Value |
| :--- | :--- |
| Record Type | `CNAME` |
| Host / Name | `app` or `cnc` |
| Target / Value | The unique host address provided by your deployment platform, such as `your-app-name.onrender.com` |
| TTL | `Automatic` or `1 Hour` |

Example:

```text
Type:  CNAME
Name:  app
Value: your-app-name.onrender.com
TTL:   Auto
```

### Option 2: Configuring the Apex or Root Domain

If your app must serve users from the root address, such as `yourdomain.com`, set up an **A Record** only if your hosting provider gives you a static IP address.

| Field | Value |
| :--- | :--- |
| Record Type | `A` |
| Host / Name | `@` |
| Target / Value | Static IP address provided by the host |
| TTL | `Automatic` or `1 Hour` |

Example:

```text
Type:  A
Name:  @
Value: 123.45.67.89
TTL:   Auto
```

### Important DNS Note

Do not guess the final CNAME or A record value. Your hosting provider will display the exact DNS record to use after you add the custom domain in its dashboard.

For most deployments, the recommended setup is:

```text
app.yourdomain.com  -> frontend
api.yourdomain.com  -> backend
```

Then configure:

```text
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com
VEINCAD_CORS_ORIGINS=https://app.yourdomain.com
```
