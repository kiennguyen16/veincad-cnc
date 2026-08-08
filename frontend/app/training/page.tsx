"use client";

/* eslint-disable @next/next/no-img-element */

import {
  ArrowLeft,
  BadgeCheck,
  BrainCircuit,
  CircleAlert,
  FileImage,
  ImageIcon,
  Layers3,
  LoaderCircle,
  Trash2,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import {
  TrainingSample,
  TrainingStyleId,
  TrainingSummary,
  apiUrl,
  createTrainingSample,
  deleteTrainingSample,
  getMe,
  getTrainingSamples,
  getTrainingSummary,
} from "@/lib/api";

const ADMIN_EMAIL = "slokermoliti@gmail.com";
const STYLE_OPTIONS: Array<{ id: TrainingStyleId; name: string; description: string }> = [
  {
    id: "centerline",
    name: "Continuous CNC",
    description: "Long, connected toolpaths with fewer small fragments.",
  },
  {
    id: "high_detail",
    name: "Fine Detail",
    description: "Smaller branches and more of the original vein texture.",
  },
];

type Language = "en" | "vi";

const TEXT = {
  en: {
    title: "Model Training",
    subtitle: "Build a labelled vein dataset",
    workspace: "Workspace",
    source: "Original slab image",
    sourceHint: "The unedited photo used as model input",
    label: "Correct vein drawing",
    labelHint: "A clean black-and-white mask or traced result",
    choose: "Choose image",
    replace: "Replace image",
    targetStyle: "Target style",
    notes: "Notes",
    notesPlaceholder: "Stone type, lighting, difficult areas...",
    addPair: "Add training pair",
    adding: "Saving pair",
    dataset: "Training dataset",
    examples: "examples",
    empty: "No labelled examples have been added yet.",
    readiness: "Dataset readiness",
    ready: "Ready for a first training run",
    collecting: "Collecting labelled examples",
    target: "Target",
    eachStyle: "approved pairs per style",
    deleteConfirm: "Remove this training pair?",
    accessDenied: "Only the administrator can manage model training data.",
    loadFailed: "Unable to load training data.",
    saveFailed: "Unable to save this training pair.",
    deleteFailed: "Unable to remove this training pair.",
    original: "Original",
    expected: "Expected",
  },
  vi: {
    title: "Huấn luyện mô hình",
    subtitle: "Xây dựng bộ dữ liệu vân đá có nhãn",
    workspace: "Không gian làm việc",
    source: "Ảnh tấm đá gốc",
    sourceHint: "Ảnh chưa chỉnh sửa dùng làm đầu vào cho mô hình",
    label: "Bản vẽ vân đá đúng",
    labelHint: "Mặt nạ đen trắng sạch hoặc kết quả đã dò",
    choose: "Chọn ảnh",
    replace: "Thay ảnh",
    targetStyle: "Kiểu kết quả",
    notes: "Ghi chú",
    notesPlaceholder: "Loại đá, ánh sáng, vùng khó...",
    addPair: "Thêm cặp huấn luyện",
    adding: "Đang lưu",
    dataset: "Bộ dữ liệu huấn luyện",
    examples: "mẫu",
    empty: "Chưa có mẫu có nhãn.",
    readiness: "Mức sẵn sàng",
    ready: "Đã sẵn sàng cho lần huấn luyện đầu tiên",
    collecting: "Đang thu thập mẫu có nhãn",
    target: "Mục tiêu",
    eachStyle: "cặp đã duyệt cho mỗi kiểu",
    deleteConfirm: "Xóa cặp huấn luyện này?",
    accessDenied: "Chỉ quản trị viên được quản lý dữ liệu huấn luyện.",
    loadFailed: "Không thể tải dữ liệu huấn luyện.",
    saveFailed: "Không thể lưu cặp huấn luyện này.",
    deleteFailed: "Không thể xóa cặp huấn luyện này.",
    original: "Ảnh gốc",
    expected: "Kết quả đúng",
  },
} satisfies Record<Language, Record<string, string>>;

function resolveAssetUrl(path: string): string {
  return /^https?:\/\//i.test(path) ? path : apiUrl(path);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function TrainingPage() {
  const [language, setLanguage] = useState<Language>("en");
  const [samples, setSamples] = useState<TrainingSample[]>([]);
  const [summary, setSummary] = useState<TrainingSummary | null>(null);
  const [sourceImage, setSourceImage] = useState<File | null>(null);
  const [labelImage, setLabelImage] = useState<File | null>(null);
  const [styleId, setStyleId] = useState<TrainingStyleId>("centerline");
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = TEXT[language];

  const sourcePreview = useMemo(() => (sourceImage ? URL.createObjectURL(sourceImage) : null), [sourceImage]);
  const labelPreview = useMemo(() => (labelImage ? URL.createObjectURL(labelImage) : null), [labelImage]);

  useEffect(() => {
    return () => {
      if (sourcePreview) URL.revokeObjectURL(sourcePreview);
      if (labelPreview) URL.revokeObjectURL(labelPreview);
    };
  }, [sourcePreview, labelPreview]);

  async function refreshTrainingData() {
    const [nextSamples, nextSummary] = await Promise.all([getTrainingSamples(), getTrainingSummary()]);
    setSamples(nextSamples);
    setSummary(nextSummary);
  }

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const auth = await getMe();
        const admin = auth.user.email.toLowerCase() === ADMIN_EMAIL;
        if (!active) return;
        setIsAdmin(admin);
        if (!admin) {
          setError(TEXT[language].accessDenied);
          return;
        }
        await refreshTrainingData();
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : TEXT[language].loadFailed);
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
    // Authentication and initial data load only run once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleImageChange(
    event: ChangeEvent<HTMLInputElement>,
    setter: (file: File | null) => void,
  ) {
    setter(event.target.files?.[0] ?? null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sourceImage || !labelImage) return;

    setIsSaving(true);
    setError(null);
    try {
      await createTrainingSample(sourceImage, labelImage, styleId, notes);
      setSourceImage(null);
      setLabelImage(null);
      setNotes("");
      await refreshTrainingData();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : t.saveFailed);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete(sample: TrainingSample) {
    if (!window.confirm(t.deleteConfirm)) return;

    setDeletingId(sample.id);
    setError(null);
    try {
      await deleteTrainingSample(sample.id);
      await refreshTrainingData();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : t.deleteFailed);
    } finally {
      setDeletingId(null);
    }
  }

  const required = summary?.required_per_style ?? 20;

  return (
    <main className="trainingShell">
      <header className="topbar trainingTopbar">
        <div className="brandBlock">
          <div className="brandMark" aria-hidden="true">
            <img className="brandLogo" src="/stone-logo.png" alt="" />
          </div>
          <div>
            <h1>{t.title}</h1>
            <p>{t.subtitle}</p>
          </div>
        </div>
        <div className="statusStrip">
          <button
            className="languageButton"
            type="button"
            onClick={() => setLanguage(language === "en" ? "vi" : "en")}
          >
            {language === "en" ? "VI" : "EN"}
          </button>
          <Link className="ghostButton trainingBackButton" href="/">
            <ArrowLeft size={17} />
            {t.workspace}
          </Link>
        </div>
      </header>

      {isLoading && (
        <section className="adminNotice">
          <LoaderCircle className="spin" size={20} />
          <span>{t.loadFailed.replace("Unable to load", "Loading")}</span>
        </section>
      )}

      {!isLoading && error && (
        <div className="alert" role="alert">
          <CircleAlert size={18} />
          <span>{error}</span>
        </div>
      )}

      {!isLoading && isAdmin && (
        <>
          <section className={`trainingReadiness ${summary?.ready_to_train ? "ready" : ""}`}>
            <div className="trainingReadinessCopy">
              {summary?.ready_to_train ? <BadgeCheck size={24} /> : <BrainCircuit size={24} />}
              <div>
                <span>{t.readiness}</span>
                <h2>{summary?.ready_to_train ? t.ready : t.collecting}</h2>
                <p>
                  {t.target}: {required} {t.eachStyle}
                </p>
              </div>
            </div>
            <strong>{summary?.total_samples ?? 0}</strong>
          </section>

          <section className="trainingLayout">
            <form className="trainingUploadPanel" onSubmit={handleSubmit}>
              <div className="panelHeader">
                <UploadCloud size={18} />
                <h2>{t.addPair}</h2>
              </div>

              <div className="trainingPairInputs">
                <TrainingFileInput
                  id="training-source"
                  title={t.source}
                  hint={t.sourceHint}
                  file={sourceImage}
                  preview={sourcePreview}
                  chooseLabel={t.choose}
                  replaceLabel={t.replace}
                  onChange={(event) => handleImageChange(event, setSourceImage)}
                />
                <TrainingFileInput
                  id="training-label"
                  title={t.label}
                  hint={t.labelHint}
                  file={labelImage}
                  preview={labelPreview}
                  chooseLabel={t.choose}
                  replaceLabel={t.replace}
                  onChange={(event) => handleImageChange(event, setLabelImage)}
                />
              </div>

              <fieldset className="trainingStyleFieldset">
                <legend>{t.targetStyle}</legend>
                <div className="trainingStyleSwitch">
                  {STYLE_OPTIONS.map((style) => (
                    <button
                      key={style.id}
                      className={styleId === style.id ? "selected" : ""}
                      type="button"
                      onClick={() => setStyleId(style.id)}
                      aria-pressed={styleId === style.id}
                    >
                      <span>{style.name}</span>
                      <small>{style.description}</small>
                    </button>
                  ))}
                </div>
              </fieldset>

              <label className="trainingNotes">
                <span>{t.notes}</span>
                <textarea
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder={t.notesPlaceholder}
                  maxLength={500}
                />
              </label>

              <button
                className="primaryButton trainingSubmit"
                type="submit"
                disabled={isSaving || !sourceImage || !labelImage}
              >
                {isSaving ? <LoaderCircle className="spin" size={18} /> : <Layers3 size={18} />}
                {isSaving ? t.adding : t.addPair}
              </button>
            </form>

            <section className="trainingDatasetPanel">
              <div className="trainingDatasetHeader">
                <div className="panelHeader">
                  <BrainCircuit size={18} />
                  <h2>{t.dataset}</h2>
                </div>
                <span>{samples.length} {t.examples}</span>
              </div>

              <div className="trainingStyleProgress">
                {STYLE_OPTIONS.map((style) => {
                  const count = summary?.counts_by_style?.[style.id] ?? 0;
                  const progress = Math.min(100, Math.round((count / required) * 100));
                  return (
                    <div key={style.id}>
                      <span>
                        <strong>{style.name}</strong>
                        {count}/{required}
                      </span>
                      <div className="trainingProgressTrack" aria-label={`${style.name}: ${progress}%`}>
                        <i style={{ width: `${progress}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>

              {samples.length === 0 ? (
                <div className="trainingEmpty">
                  <ImageIcon size={28} />
                  <p>{t.empty}</p>
                </div>
              ) : (
                <div className="trainingSampleList">
                  {samples.map((sample) => (
                    <article className="trainingSampleCard" key={sample.id}>
                      <div className="trainingSampleImages">
                        <figure>
                          <img src={resolveAssetUrl(sample.source_image_url)} alt={sample.source_original_filename} />
                          <figcaption>{t.original}</figcaption>
                        </figure>
                        <figure>
                          <img src={resolveAssetUrl(sample.label_image_url)} alt={sample.label_original_filename} />
                          <figcaption>{t.expected}</figcaption>
                        </figure>
                      </div>
                      <div className="trainingSampleMeta">
                        <div>
                          <strong>
                            {STYLE_OPTIONS.find((style) => style.id === sample.style_id)?.name ?? sample.style_id}
                          </strong>
                          <span>{formatDate(sample.created_at)}</span>
                          {sample.notes && <p>{sample.notes}</p>}
                        </div>
                        <button
                          type="button"
                          onClick={() => handleDelete(sample)}
                          disabled={deletingId === sample.id}
                          aria-label={t.deleteConfirm}
                          title={t.deleteConfirm}
                        >
                          {deletingId === sample.id ? (
                            <LoaderCircle className="spin" size={17} />
                          ) : (
                            <Trash2 size={17} />
                          )}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </section>
        </>
      )}
    </main>
  );
}

type TrainingFileInputProps = {
  id: string;
  title: string;
  hint: string;
  file: File | null;
  preview: string | null;
  chooseLabel: string;
  replaceLabel: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
};

function TrainingFileInput({
  id,
  title,
  hint,
  file,
  preview,
  chooseLabel,
  replaceLabel,
  onChange,
}: TrainingFileInputProps) {
  return (
    <div className="trainingFileControl">
      <div>
        <strong>{title}</strong>
        <span>{hint}</span>
      </div>
      <label htmlFor={id} className={preview ? "hasPreview" : ""}>
        {preview ? <img src={preview} alt={file?.name ?? title} /> : <FileImage size={28} />}
        <span>{preview ? replaceLabel : chooseLabel}</span>
        <small>{file?.name ?? "PNG, JPEG, WEBP, BMP, TIFF"}</small>
      </label>
      <input
        id={id}
        className="hiddenInput"
        type="file"
        accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff"
        onChange={onChange}
      />
    </div>
  );
}
