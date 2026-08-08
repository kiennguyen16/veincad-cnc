"use client";

import {
  Activity,
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  Database,
  FileImage,
  FolderOpen,
  HardDrive,
  KeyRound,
  LoaderCircle,
  Mail,
  MessageSquare,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { AdminSummary, User, createAdminUser, getAdminSummary, getMe } from "@/lib/api";

const ADMIN_EMAIL = "slokermoliti@gmail.com";

export default function AdminPage() {
  const [user, setUser] = useState<User | null>(null);
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [createUserError, setCreateUserError] = useState<string | null>(null);
  const [createUserMessage, setCreateUserMessage] = useState<string | null>(null);
  const [isCreatingUser, setIsCreatingUser] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadAdmin() {
      try {
        const auth = await getMe();
        if (!active) {
          return;
        }
        setUser(auth.user);

        if (auth.user.email.toLowerCase() !== ADMIN_EMAIL) {
          setError("Access denied. This page is only available to slokermoliti@gmail.com.");
          return;
        }

        const adminSummary = await getAdminSummary();
        if (!active) {
          return;
        }
        setSummary(adminSummary);
      } catch (loadError) {
        if (!active) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Unable to load the admin page.");
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    loadAdmin();
    return () => {
      active = false;
    };
  }, []);

  const isAdmin = user?.email.toLowerCase() === ADMIN_EMAIL;

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateUserError(null);
    setCreateUserMessage(null);
    setIsCreatingUser(true);

    try {
      const createdUser = await createAdminUser(newUserEmail.trim(), newUserPassword);
      setCreateUserMessage(`${createdUser.email} can now sign in.`);
      setNewUserEmail("");
      setNewUserPassword("");
      setSummary(await getAdminSummary());
    } catch (createError) {
      setCreateUserError(createError instanceof Error ? createError.message : "Unable to create this user.");
    } finally {
      setIsCreatingUser(false);
    }
  }

  return (
    <main className="adminShell">
      <header className="topbar adminTopbar">
        <div className="brandBlock">
          <div className="brandMark" aria-hidden="true">
            <img className="brandLogo" src="/stone-logo.png" alt="" />
          </div>
          <div>
            <h1>Admin</h1>
            <p>VeinCAD CNC control room</p>
          </div>
        </div>
        <a className="ghostButton adminBackButton" href="/">
          <ArrowLeft size={17} />
          Workspace
        </a>
      </header>

      {isLoading && (
        <section className="adminNotice">
          <Activity className="spin" size={20} />
          <span>Loading admin data...</span>
        </section>
      )}

      {!isLoading && error && (
        <section className="adminNotice denied">
          <ShieldCheck size={22} />
          <div>
            <h2>{isAdmin ? "Admin data unavailable" : "Access denied"}</h2>
            <p>{error}</p>
            {!user && (
              <a className="primaryButton adminInlineButton" href="/">
                Sign in
              </a>
            )}
          </div>
        </section>
      )}

      {!isLoading && summary && isAdmin && (
        <>
          <section className="adminHero">
            <div>
              <span>Administrator</span>
              <h2>{summary.admin_email}</h2>
              <p>{summary.storage_path}</p>
            </div>
            <ShieldCheck size={38} />
          </section>

          <section className="adminPanel adminCreatePanel">
            <div className="panelHeader">
              <UserPlus size={18} />
              <h2>Add User</h2>
            </div>
            <form className="adminCreateForm" onSubmit={handleCreateUser}>
              <label>
                <span>Email</span>
                <div className="inputWithIcon">
                  <Mail size={18} />
                  <input
                    type="email"
                    value={newUserEmail}
                    onChange={(event) => setNewUserEmail(event.target.value)}
                    placeholder="newuser@example.com"
                    required
                    autoComplete="off"
                  />
                </div>
              </label>
              <label>
                <span>Temporary Password</span>
                <div className="inputWithIcon">
                  <KeyRound size={18} />
                  <input
                    type="password"
                    value={newUserPassword}
                    onChange={(event) => setNewUserPassword(event.target.value)}
                    placeholder="Minimum 6 characters"
                    required
                    minLength={6}
                    autoComplete="new-password"
                  />
                </div>
              </label>
              <button
                className="primaryButton adminCreateButton"
                type="submit"
                disabled={isCreatingUser || !newUserEmail.trim() || newUserPassword.length < 6}
              >
                {isCreatingUser ? <LoaderCircle className="spin" size={18} /> : <UserPlus size={18} />}
                {isCreatingUser ? "Creating" : "Create User"}
              </button>
            </form>
            {createUserMessage && (
              <div className="adminFormMessage success" role="status">
                <CheckCircle2 size={17} />
                <span>{createUserMessage}</span>
              </div>
            )}
            {createUserError && (
              <div className="adminFormMessage error" role="alert">
                <CircleAlert size={17} />
                <span>{createUserError}</span>
              </div>
            )}
          </section>

          <section className="adminStatsGrid">
            <AdminStat icon={<Users size={20} />} label="Users" value={summary.user_count.toLocaleString()} />
            <AdminStat
              icon={<Activity size={20} />}
              label="Active Sessions"
              value={summary.active_session_count.toLocaleString()}
            />
            <AdminStat
              icon={<FileImage size={20} />}
              label="Uploads"
              value={summary.upload_count.toLocaleString()}
            />
            <AdminStat
              icon={<FolderOpen size={20} />}
              label="Folders"
              value={summary.folder_count.toLocaleString()}
            />
            <AdminStat icon={<Database size={20} />} label="Jobs" value={summary.job_count.toLocaleString()} />
            <AdminStat
              icon={<MessageSquare size={20} />}
              label="CAD Messages"
              value={summary.dxf_message_count.toLocaleString()}
            />
            <AdminStat
              icon={<ShieldCheck size={20} />}
              label="DXF Revisions"
              value={summary.dxf_revision_count.toLocaleString()}
            />
            <AdminStat
              icon={<HardDrive size={20} />}
              label="Storage"
              value={`${formatBytes(summary.storage_bytes)} / ${formatBytes(summary.storage_quota_bytes)}`}
              detail={`${summary.storage_usage_percent.toFixed(1)}% used, ${formatBytes(summary.storage_available_bytes)} free`}
            />
          </section>

          <section className="adminPanel">
            <div className="panelHeader">
              <FileImage size={18} />
              <h2>Recent Uploads</h2>
            </div>
            {summary.latest_uploads.length > 0 ? (
              <div className="adminTableWrap">
                <table className="adminTable">
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Folder</th>
                      <th>User</th>
                      <th>Job</th>
                      <th>Uploaded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.latest_uploads.map((upload) => (
                      <tr key={upload.id}>
                        <td>{upload.original_filename}</td>
                        <td>{upload.folder_name ?? "Unfiled"}</td>
                        <td>{upload.user_email}</td>
                        <td>{upload.generated_job_id ?? "Pending"}</td>
                        <td>{formatDate(upload.upload_timestamp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="adminEmpty">No uploads yet.</p>
            )}
          </section>
        </>
      )}
    </main>
  );
}

function AdminStat({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <article className="adminStatCard">
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
