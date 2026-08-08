"use client";

/* eslint-disable @next/next/no-img-element */

import {
  BadgeCheck,
  BrainCircuit,
  CircleAlert,
  Download,
  FileImage,
  FolderOpen,
  FolderPlus,
  Gauge,
  HardDrive,
  ImageIcon,
  LockKeyhole,
  LogOut,
  Mail,
  MessageSquare,
  LoaderCircle,
  RefreshCcw,
  Ruler,
  Send,
  Settings2,
  ShieldCheck,
  UploadCloud,
  UserCircle,
  Wand2,
  X,
} from "lucide-react";
import { ChangeEvent, DragEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE_URL,
  DxfChatMessage,
  ProcessResponse,
  ProcessSettings,
  SampleImage,
  StorageFolder,
  StylePreset,
  UploadRecord,
  User,
  apiUrl,
  configureProcessing,
  createFolder,
  getFolders,
  getHealth,
  getJob,
  getMe,
  getSamples,
  getStyles,
  getUploads,
  login,
  logout,
  modifyDxf,
  processImage,
  processSample,
} from "@/lib/api";

const MAX_FILE_SIZE_MB = 25;
const ADMIN_EMAIL = "slokermoliti@gmail.com";
const LAST_JOB_STORAGE_KEY = "veincad:lastJobId:v2";
const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"];

type PreviewMode = "preview" | "mask";
type Language = "en" | "vi";

const SAMPLE_HINTS: Record<Language, Record<string, string>> = {
  en: {
    "sample_01.png": "Logo",
    "sample_02.png": "Overlay",
    "sample_03.png": "Overlay",
    "sample_04.png": "Mask",
    "sample_05.jpg": "Raw slab",
    "sample_06.jpg": "Low contrast",
    "sample_07.jpg": "Raw slab",
  },
  vi: {
    "sample_01.png": "Logo",
    "sample_02.png": "Lớp đánh dấu",
    "sample_03.png": "Lớp đánh dấu",
    "sample_04.png": "Mặt nạ",
    "sample_05.jpg": "Tấm đá thô",
    "sample_06.jpg": "Tương phản thấp",
    "sample_07.jpg": "Tấm đá thô",
  },
};

const TRANSLATIONS = {
  en: {
    signInSubtitle: "Sign in to trace slab veins and export DXF files.",
    email: "Email",
    password: "Password",
    forgotPassword: "Forgot password?",
    signIn: "Sign In",
    signingIn: "Signing in",
    source: "Source",
    uploadSlabImage: "Upload slab image",
    samples: "Samples",
    storageRepo: "Storage Repo",
    newFolder: "New folder",
    create: "Create",
    folder: "Folder",
    uploads: "Uploads",
    noUploads: "No uploads in this folder yet.",
    traceStyle: "Trace Style",
    processing: "Processing",
    sensitivity: "Sensitivity",
    noiseFilter: "Noise filter",
    simplify: "Simplify",
    dxfScale: "DXF Scale",
    widthMm: "Width mm",
    heightMm: "Height mm",
    traceImage: "Trace Image",
    tracing: "Tracing",
    reset: "Reset",
    preview: "Preview",
    mask: "Mask",
    noImage: "No image selected",
    selectImage: "Select a slab photo or sample",
    lines: "Lines",
    length: "Length",
    scale: "Scale",
    time: "Time",
    dxfReady: "DXF ready",
    revisedDxfReady: "Revised DXF ready",
    dxfOutput: "DXF output",
    downloadDxf: "Download DXF",
    cadChat: "CAD Chat",
    chatPlaceholder: "Add a 10mm border...",
    chatEmpty: "Generate a DXF, then ask for edits like adding a 10mm border or smoothing lines.",
    logout: "Log out",
  },
  vi: {
    signInSubtitle: "Đăng nhập để dò vân đá và xuất file DXF.",
    email: "Email",
    password: "Mật khẩu",
    forgotPassword: "Quên mật khẩu?",
    signIn: "Đăng nhập",
    signingIn: "Đang đăng nhập",
    source: "Nguồn ảnh",
    uploadSlabImage: "Tải ảnh tấm đá",
    samples: "Ảnh mẫu",
    storageRepo: "Kho lưu trữ",
    newFolder: "Thư mục mới",
    create: "Tạo",
    folder: "Thư mục",
    uploads: "Ảnh đã tải",
    noUploads: "Chưa có ảnh trong thư mục này.",
    traceStyle: "Kiểu dò vân",
    processing: "Xử lý",
    sensitivity: "Độ nhạy",
    noiseFilter: "Lọc nhiễu",
    simplify: "Đơn giản hóa",
    dxfScale: "Tỷ lệ DXF",
    widthMm: "Rộng mm",
    heightMm: "Cao mm",
    traceImage: "Dò ảnh",
    tracing: "Đang dò",
    reset: "Đặt lại",
    preview: "Xem trước",
    mask: "Mặt nạ",
    noImage: "Chưa chọn ảnh",
    selectImage: "Chọn ảnh tấm đá hoặc ảnh mẫu",
    lines: "Đường",
    length: "Chiều dài",
    scale: "Tỷ lệ",
    time: "Thời gian",
    dxfReady: "DXF đã sẵn sàng",
    revisedDxfReady: "DXF chỉnh sửa đã sẵn sàng",
    dxfOutput: "Đầu ra DXF",
    downloadDxf: "Tải DXF",
    cadChat: "Chat CAD",
    chatPlaceholder: "Thêm viền 10mm...",
    chatEmpty: "Tạo DXF trước, sau đó yêu cầu thêm viền 10mm hoặc làm mượt đường vân.",
    logout: "Đăng xuất",
  },
} satisfies Record<Language, Record<string, string>>;

void TRANSLATIONS;

const UI_TEXT = {
  en: {
    signInSubtitle: "Sign in to trace slab veins and export DXF files.",
    tagline: "Stone vein tracing to DXF",
    email: "Email",
    password: "Password",
    forgotPassword: "Forgot password?",
    signIn: "Sign In",
    signingIn: "Signing in",
    onlyImages: "Only PNG, JPEG, WEBP, BMP, and TIFF images are supported.",
    imageTooLarge: `Image must be ${MAX_FILE_SIZE_MB} MB or smaller.`,
    emptyFile: "The selected file is empty.",
    unusableFile: "This file cannot be used.",
    backendUnavailable: "The backend is not available.",
    loginFailed: "Login failed.",
    createFolderFailed: "Could not create folder.",
    openUploadFailed: "Could not open upload job.",
    loadUploadsFailed: "Could not load uploads for this folder.",
    selectImageFirst: "Select an image first.",
    processingFailed: "Processing failed.",
    dxfGeneratedMessage: "DXF generated. Tell me what to adjust, such as add a 10mm border or smooth the vein lines.",
    cadEditFailed: "CAD edit failed.",
    cadEditFailedMessage: "I could not apply that DXF edit. Try a simpler instruction.",
    imageConfigFailed: "Image configuration failed.",
    source: "Source",
    uploadSlabImage: "Upload slab image",
    fileTypes: "PNG, JPEG, WEBP, BMP, TIFF",
    samples: "Samples",
    storageRepo: "Storage Repo",
    newFolder: "New folder",
    create: "Create",
    folder: "Folder",
    uploads: "Uploads",
    noUploads: "No uploads in this folder yet.",
    selectedSource: "Selected source",
    clear: "Clear",
    traceStyle: "Trace Style",
    traceStyleAria: "Trace style",
    processing: "Processing",
    sensitivity: "Sensitivity",
    noiseFilter: "Noise filter",
    simplify: "Simplify",
    dxfScale: "DXF Scale",
    widthMm: "Width mm",
    heightMm: "Height mm",
    traceImage: "Trace Image",
    tracing: "Tracing",
    reset: "Reset",
    preview: "Preview",
    mask: "Mask",
    noImage: "No image selected",
    selectImage: "Select a slab photo or sample",
    sourceWaitingAlt: "Source waiting to be traced",
    resultAlt: "result",
    revisedPreview: "Revised DXF Preview",
    previewTypeAria: "Preview type",
    lines: "Lines",
    length: "Length",
    scale: "Scale",
    time: "Time",
    pending: "Pending",
    dxfReady: "DXF ready",
    revisedDxfReady: "Revised DXF ready",
    dxfOutput: "DXF output",
    downloadDxf: "Download DXF",
    workArea: "Work area",
    scaleIsOne: "Scale is using 1 mm per pixel",
    traceToCreate: "Trace an image to create a downloadable file",
    cadChat: "CAD Chat",
    openCadChat: "Open CAD chat",
    closeCadChat: "Close CAD chat",
    chatPlaceholder: "Clean the image, or add a 10mm border...",
    chatEmpty: "Ask me to configure extraction settings, or generate a DXF and request CAD edits.",
    you: "You",
    cadAssistant: "CAD assistant",
    sendCadEdit: "Send CAD edit",
    admin: "Admin",
    training: "Training",
    logout: "Log out",
    backend: "Backend",
  },
  vi: {
    signInSubtitle: "Đăng nhập để dò vân đá và xuất file DXF.",
    tagline: "Dò vân đá và xuất DXF",
    email: "Email",
    password: "Mật khẩu",
    forgotPassword: "Quên mật khẩu?",
    signIn: "Đăng nhập",
    signingIn: "Đang đăng nhập",
    onlyImages: "Chỉ hỗ trợ ảnh PNG, JPEG, WEBP, BMP và TIFF.",
    imageTooLarge: `Ảnh phải nhỏ hơn hoặc bằng ${MAX_FILE_SIZE_MB} MB.`,
    emptyFile: "Tệp đã chọn đang trống.",
    unusableFile: "Không thể dùng tệp này.",
    backendUnavailable: "Backend chưa sẵn sàng.",
    loginFailed: "Đăng nhập thất bại.",
    createFolderFailed: "Không thể tạo thư mục.",
    openUploadFailed: "Không thể mở tác vụ của ảnh đã tải.",
    loadUploadsFailed: "Không thể tải danh sách ảnh trong thư mục này.",
    selectImageFirst: "Hãy chọn ảnh trước.",
    processingFailed: "Xử lý thất bại.",
    dxfGeneratedMessage: "DXF đã được tạo. Hãy cho tôi biết cần chỉnh gì, ví dụ thêm viền 10mm hoặc làm mượt đường vân.",
    cadEditFailed: "Chỉnh CAD thất bại.",
    cadEditFailedMessage: "Tôi chưa áp dụng được chỉnh sửa DXF đó. Hãy thử yêu cầu đơn giản hơn.",
    imageConfigFailed: "Cấu hình ảnh thất bại.",
    source: "Nguồn ảnh",
    uploadSlabImage: "Tải ảnh tấm đá",
    fileTypes: "PNG, JPEG, WEBP, BMP, TIFF",
    samples: "Ảnh mẫu",
    storageRepo: "Kho lưu trữ",
    newFolder: "Thư mục mới",
    create: "Tạo",
    folder: "Thư mục",
    uploads: "Ảnh đã tải",
    noUploads: "Chưa có ảnh trong thư mục này.",
    selectedSource: "Nguồn ảnh đã chọn",
    clear: "Xóa",
    traceStyle: "Kiểu dò vân",
    traceStyleAria: "Kiểu dò vân",
    processing: "Xử lý",
    sensitivity: "Độ nhạy",
    noiseFilter: "Lọc nhiễu",
    simplify: "Đơn giản hóa",
    dxfScale: "Tỷ lệ DXF",
    widthMm: "Rộng mm",
    heightMm: "Cao mm",
    traceImage: "Dò ảnh",
    tracing: "Đang dò",
    reset: "Đặt lại",
    preview: "Xem trước",
    mask: "Mặt nạ",
    noImage: "Chưa chọn ảnh",
    selectImage: "Chọn ảnh tấm đá hoặc ảnh mẫu",
    sourceWaitingAlt: "Nguồn ảnh đang chờ dò",
    resultAlt: "kết quả",
    revisedPreview: "Xem trước DXF đã chỉnh",
    previewTypeAria: "Kiểu xem trước",
    lines: "Đường",
    length: "Chiều dài",
    scale: "Tỷ lệ",
    time: "Thời gian",
    pending: "Đang chờ",
    dxfReady: "DXF đã sẵn sàng",
    revisedDxfReady: "DXF chỉnh sửa đã sẵn sàng",
    dxfOutput: "Đầu ra DXF",
    downloadDxf: "Tải DXF",
    workArea: "Vùng làm việc",
    scaleIsOne: "Tỷ lệ đang dùng 1 mm cho mỗi pixel",
    traceToCreate: "Dò ảnh để tạo tệp có thể tải xuống",
    cadChat: "Chat CAD",
    openCadChat: "Mở Chat CAD",
    closeCadChat: "Đóng Chat CAD",
    chatPlaceholder: "Làm sạch ảnh, hoặc thêm viền 10mm...",
    chatEmpty: "Bạn có thể yêu cầu cấu hình cách dò ảnh, hoặc tạo DXF rồi yêu cầu chỉnh CAD.",
    you: "Bạn",
    cadAssistant: "Trợ lý CAD",
    sendCadEdit: "Gửi chỉnh sửa CAD",
    admin: "Admin",
    training: "Huáº¥n luyá»‡n",
    logout: "Đăng xuất",
    backend: "Backend",
  },
} satisfies Record<Language, Record<string, string>>;

export default function Home() {
  const [styles, setStyles] = useState<StylePreset[]>([]);
  const [samples, setSamples] = useState<SampleImage[]>([]);
  const [folders, setFolders] = useState<StorageFolder[]>([]);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedSample, setSelectedSample] = useState<SampleImage | null>(null);
  const [sourcePreviewUrl, setSourcePreviewUrl] = useState<string | null>(null);
  const [sourceObjectUrl, setSourceObjectUrl] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessResponse | null>(null);
  const [modifiedPreviewUrl, setModifiedPreviewUrl] = useState<string | null>(null);
  const [modifiedDxfUrl, setModifiedDxfUrl] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<DxfChatMessage[]>([]);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("preview");
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [isChatting, setIsChatting] = useState(false);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loginEmail, setLoginEmail] = useState("slokermoliti@gmail.com");
  const [loginPassword, setLoginPassword] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [settings, setSettings] = useState<ProcessSettings>({
    styleId: "centerline",
    sensitivity: 0.64,
    noiseFilter: 2,
    simplifyTolerance: 1.6,
    slabWidthMm: 3200,
    slabHeightMm: 1600,
  });
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRequestIdRef = useRef(0);

  const activeStyle = useMemo(
    () => styles.find((style) => style.id === settings.styleId),
    [settings.styleId, styles],
  );
  const visibleStyles = useMemo(
    () => styles.filter((style) => style.id === "centerline" || style.id === "high_detail"),
    [styles],
  );
  const t = UI_TEXT[language];

  async function loadWorkspaceData() {
    const [styleList, sampleList, folderList] = await Promise.all([getStyles(), getSamples(), getFolders()]);
    setStyles(styleList);
    setSamples(sampleList);
    setFolders(folderList);
    const nextFolderId = selectedFolderId ?? folderList[0]?.id ?? null;
    setSelectedFolderId(nextFolderId);
    setUploads(await getUploads(nextFolderId));

    window.localStorage.removeItem("veincad:lastJobId");
    const savedJobId = window.localStorage.getItem(LAST_JOB_STORAGE_KEY);
    if (savedJobId) {
      try {
        const savedJob = await getJob(savedJobId);
        setResult(savedJob);
      } catch {
        window.localStorage.removeItem(LAST_JOB_STORAGE_KEY);
      }
    }
  }

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      try {
        await getHealth();
        if (!active) {
          return;
        }
        try {
          const auth = await getMe();
          if (!active) {
            return;
          }
          setUser(auth.user);
          await loadWorkspaceData();
        } catch {
          window.localStorage.removeItem(LAST_JOB_STORAGE_KEY);
        }
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : t.backendUnavailable);
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    bootstrap();

    return () => {
      active = false;
    };
    // The initial auth/bootstrap check should only run once; login/logout trigger their own refreshes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      if (sourceObjectUrl) {
        URL.revokeObjectURL(sourceObjectUrl);
      }
    };
  }, [sourceObjectUrl]);

  function updateSelectedFile(file: File, sampleName: string | null = null) {
    validateFile(file);
    if (sourceObjectUrl) {
      URL.revokeObjectURL(sourceObjectUrl);
    }
    const objectUrl = URL.createObjectURL(file);
    setSelectedFile(file);
    setSelectedSample(sampleName ? { name: sampleName, url: "" } : null);
    setSourcePreviewUrl(objectUrl);
    setSourceObjectUrl(objectUrl);
    setResult(null);
    setModifiedPreviewUrl(null);
    setModifiedDxfUrl(null);
    setChatMessages([]);
    setError(null);
  }

  function validateFile(file: File) {
    if (!ACCEPTED_TYPES.includes(file.type) && !file.name.match(/\.(png|jpe?g|webp|bmp|tiff?)$/i)) {
      throw new Error(t.onlyImages);
    }
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      throw new Error(t.imageTooLarge);
    }
    if (file.size === 0) {
      throw new Error(t.emptyFile);
    }
  }

  function handleFiles(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file) {
      return;
    }
    try {
      updateSelectedFile(file);
    } catch (fileError) {
      setError(fileError instanceof Error ? fileError.message : t.unusableFile);
    }
  }

  function handleDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setIsDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  function handleStyleChange(styleId: string) {
    const style = styles.find((item) => item.id === styleId);
    setSettings((current) => ({
      ...current,
      styleId,
      sensitivity: style?.default_sensitivity ?? current.sensitivity,
      noiseFilter: style?.default_noise_filter ?? current.noiseFilter,
      simplifyTolerance: style?.default_simplify_tolerance ?? current.simplifyTolerance,
    }));
  }

  async function handleLoginSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoggingIn(true);
    setError(null);
    try {
      const auth = await login(loginEmail.trim(), loginPassword);
      setUser(auth.user);
      setLoginPassword("");
      await loadWorkspaceData();
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : t.loginFailed);
    } finally {
      setIsLoggingIn(false);
      setIsLoading(false);
    }
  }

  async function handleLogout() {
    setError(null);
    try {
      await logout();
    } catch {
      // Clear the local workspace even if the server session already expired.
    }
    resetWorkspace();
    setUser(null);
    setStyles([]);
    setSamples([]);
    setFolders([]);
    setUploads([]);
    setSelectedFolderId(null);
    setChatMessages([]);
  }

  async function refreshStorage(folderId = selectedFolderId) {
    const [folderList, uploadList] = await Promise.all([getFolders(), getUploads(folderId)]);
    setFolders(folderList);
    setUploads(uploadList);
    if (folderId && folderList.some((folder) => folder.id === folderId)) {
      setSelectedFolderId(folderId);
    } else if (!folderId && folderList[0]) {
      setSelectedFolderId(folderList[0].id);
    }
  }

  async function handleCreateFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newFolderName.trim()) {
      return;
    }
    setIsCreatingFolder(true);
    setError(null);
    try {
      const folder = await createFolder(newFolderName.trim());
      setNewFolderName("");
      setSelectedFolderId(folder.id);
      await refreshStorage(folder.id);
    } catch (folderError) {
      setError(folderError instanceof Error ? folderError.message : t.createFolderFailed);
    } finally {
      setIsCreatingFolder(false);
    }
  }

  async function handleFolderChange(folderId: string) {
    const requestId = folderRequestIdRef.current + 1;
    folderRequestIdRef.current = requestId;
    setSelectedFolderId(folderId);
    setError(null);
    try {
      const uploadList = await getUploads(folderId);
      if (requestId === folderRequestIdRef.current) {
        setUploads(uploadList);
      }
    } catch (folderError) {
      if (requestId === folderRequestIdRef.current) {
        setUploads([]);
        setError(folderError instanceof Error ? folderError.message : t.loadUploadsFailed);
      }
    }
  }

  async function handleOpenUpload(upload: UploadRecord) {
    if (sourceObjectUrl) {
      URL.revokeObjectURL(sourceObjectUrl);
    }
    setSelectedFile(null);
    setSelectedSample(null);
    setSourceObjectUrl(null);
    setSourcePreviewUrl(uploadImageUrl(upload));
    setResult(null);
    setModifiedPreviewUrl(null);
    setModifiedDxfUrl(null);
    setChatMessages([]);
    setError(null);
    window.localStorage.removeItem(LAST_JOB_STORAGE_KEY);
    if (upload.generated_job_id) {
      try {
        const job = await getJob(upload.generated_job_id);
        setResult(job);
        window.localStorage.setItem(LAST_JOB_STORAGE_KEY, job.job_id);
      } catch (uploadError) {
        setError(uploadError instanceof Error ? uploadError.message : t.openUploadFailed);
      }
    }
  }

  async function handleSampleSelect(sample: SampleImage) {
    setError(null);
    if (sourceObjectUrl) {
      URL.revokeObjectURL(sourceObjectUrl);
    }
    setSelectedFile(null);
    setSelectedSample(sample);
    setSourcePreviewUrl(apiUrl(sample.url));
    setSourceObjectUrl(null);
    setResult(null);
    setModifiedPreviewUrl(null);
    setModifiedDxfUrl(null);
    setChatMessages([]);
    if (sample.name === "sample_02.png" || sample.name === "sample_03.png" || sample.name === "sample_04.png") {
      handleStyleChange("color_trace");
    }
  }

  async function handleProcess() {
    if (!selectedFile && !selectedSample) {
      setError(t.selectImageFirst);
      return;
    }

    setIsProcessing(true);
    setError(null);
    setPreviewMode("preview");

    try {
      const response = selectedFile
        ? await processImage(selectedFile, settings, selectedFolderId)
        : await processSample(selectedSample!.name, settings);
      setResult(response);
      setModifiedPreviewUrl(null);
      setModifiedDxfUrl(null);
      setChatMessages([
        {
          role: "assistant",
          content: t.dxfGeneratedMessage,
        },
      ]);
      if (selectedFile) {
        try {
          await refreshStorage(selectedFolderId);
        } catch {
          setError(t.loadUploadsFailed);
        }
      }
      window.localStorage.setItem(LAST_JOB_STORAGE_KEY, response.job_id);
    } catch (processError) {
      setError(processError instanceof Error ? processError.message : t.processingFailed);
    } finally {
      setIsProcessing(false);
    }
  }

  function resetWorkspace() {
    if (sourceObjectUrl) {
      URL.revokeObjectURL(sourceObjectUrl);
    }
    setSelectedFile(null);
    setSelectedSample(null);
    setSourcePreviewUrl(null);
    setSourceObjectUrl(null);
    setResult(null);
    setModifiedPreviewUrl(null);
    setModifiedDxfUrl(null);
    setChatMessages([]);
    setChatInput("");
    setError(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
    window.localStorage.removeItem(LAST_JOB_STORAGE_KEY);
  }

  async function handleDxfChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!chatInput.trim()) {
      return;
    }

    const userMessage: DxfChatMessage = { role: "user", content: chatInput.trim() };
    setChatMessages((current) => [...current, userMessage]);
    setChatInput("");
    setIsChatting(true);
    setError(null);

    try {
      if (!result) {
        const response = await configureProcessing(userMessage.content);
        setSettings((current) => ({
          ...current,
          styleId: response.settings.style_id,
          sensitivity: response.settings.sensitivity,
          noiseFilter: response.settings.noise_filter,
          simplifyTolerance: response.settings.simplify_tolerance,
        }));
        setChatMessages((current) => [
          ...current,
          { role: "assistant", content: response.assistant_message },
        ]);
        return;
      }

      const response = await modifyDxf(result.job_id, userMessage.content);
      setChatMessages(response.messages);
      setModifiedDxfUrl(response.dxf_url);
      if (response.preview_url) {
        setModifiedPreviewUrl(response.preview_url);
        setPreviewMode("preview");
      }
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : result ? t.cadEditFailed : t.imageConfigFailed);
      setChatMessages((current) => [
        ...current,
        { role: "assistant", content: result ? t.cadEditFailedMessage : t.imageConfigFailed },
      ]);
    } finally {
      setIsChatting(false);
    }
  }

  const previewUrl =
    modifiedPreviewUrl && previewMode === "preview"
      ? apiUrl(modifiedPreviewUrl)
      : result && previewMode === "preview"
        ? apiUrl(result.preview_url)
        : result
          ? apiUrl(result.mask_url)
          : null;
  const dxfDownloadUrl = modifiedDxfUrl ?? result?.dxf_url ?? null;
  const isAdminUser = user?.email.toLowerCase() === ADMIN_EMAIL;

  function uploadImageUrl(upload: UploadRecord): string {
    if (upload.source_image_url) {
      return apiUrl(upload.source_image_url);
    }
    const folderPart = upload.folder_id ? `${upload.folder_id}/` : "";
    return apiUrl(`/storage/uploads/slabs/${folderPart}${upload.stored_filename}`);
  }

  if (!user) {
    return (
      <main className="loginShell">
        <section className="loginPanel">
          <div className="loginBrand">
            <div className="brandMark" aria-hidden="true">
              <img className="brandLogo" src="/stone-logo.png" alt="" />
            </div>
            <div>
              <h1>VeinCAD CNC</h1>
              <p>{t.signInSubtitle}</p>
            </div>
          </div>
          <button className="languageButton loginLanguage" type="button" onClick={() => setLanguage(language === "en" ? "vi" : "en")}>
            {language === "en" ? "VI" : "EN"}
          </button>

          <form className="loginForm" onSubmit={handleLoginSubmit}>
            <label>
              <span>{t.email}</span>
              <div className="inputWithIcon">
                <Mail size={18} />
                <input
                  type="email"
                  value={loginEmail}
                  onChange={(event) => setLoginEmail(event.target.value)}
                  required
                  autoComplete="email"
                />
              </div>
            </label>
            <label>
              <span>{t.password}</span>
              <div className="inputWithIcon">
                <LockKeyhole size={18} />
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(event) => setLoginPassword(event.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>
            </label>
            <a className="authLink" href="/forgot-password">
              {t.forgotPassword ?? "Forgot password?"}
            </a>

            {error && (
              <div className="alert compact" role="alert">
                <CircleAlert size={18} />
                <span>{error}</span>
              </div>
            )}

            <button className="primaryButton loginButton" type="submit" disabled={isLoggingIn || isLoading}>
              {isLoggingIn ? <LoaderCircle className="spin" size={18} /> : <LockKeyhole size={18} />}
              {isLoggingIn ? t.signingIn : t.signIn}
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brandBlock">
          <div className="brandMark" aria-hidden="true">
            <img className="brandLogo" src="/stone-logo.png" alt="" />
          </div>
          <div>
            <h1>VeinCAD CNC</h1>
            <p>{t.tagline}</p>
          </div>
        </div>
        <div className="statusStrip">
          <button className="languageButton" type="button" onClick={() => setLanguage(language === "en" ? "vi" : "en")}>
            {language === "en" ? "VI" : "EN"}
          </button>
          <span className="statusPill">
            <UserCircle size={16} />
            {user.email}
          </span>
          {isAdminUser && (
            <>
              <a className="adminButton" href="/training">
                <BrainCircuit size={16} />
                {t.training}
              </a>
              <a className="adminButton" href="/admin">
                <ShieldCheck size={16} />
                {t.admin}
              </a>
            </>
          )}
          <button className="logoutButton" type="button" onClick={handleLogout} title={t.logout}>
            <LogOut size={16} />
            {t.logout}
          </button>
        </div>
      </header>

      <section className="workspace">
        <aside className="controlRail">
          <section className="panel uploadPanel">
            <div className="panelHeader">
              <UploadCloud size={18} />
              <h2>{t.source}</h2>
            </div>

            <button
              className={`dropZone ${isDragging ? "dragging" : ""}`}
              onClick={() => inputRef.current?.click()}
              onDragOver={(event) => {
                event.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              type="button"
            >
              <FileImage size={34} />
              <span>{selectedFile ? selectedFile.name : t.uploadSlabImage}</span>
              <small>{t.fileTypes}</small>
            </button>
            <input
              ref={inputRef}
              className="hiddenInput"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff"
              onChange={(event: ChangeEvent<HTMLInputElement>) => handleFiles(event.target.files)}
            />

            {sourcePreviewUrl && (
              <div className="sourceThumb">
                <img src={sourcePreviewUrl} alt={t.selectedSource} />
                <button type="button" onClick={resetWorkspace} aria-label={t.clear} title={t.clear}>
                  <X size={16} />
                </button>
              </div>
            )}
          </section>

          <section className="panel">
            <div className="panelHeader">
              <HardDrive size={18} />
              <h2>{t.storageRepo}</h2>
            </div>
            <label className="folderSelect">
              <span>{t.folder}</span>
              <select value={selectedFolderId ?? ""} onChange={(event) => handleFolderChange(event.target.value)}>
                {folders.map((folder) => (
                  <option key={folder.id} value={folder.id}>
                    {folder.name} ({folder.upload_count})
                  </option>
                ))}
              </select>
            </label>
            <form className="folderCreate" onSubmit={handleCreateFolder}>
              <input
                value={newFolderName}
                onChange={(event) => setNewFolderName(event.target.value)}
                placeholder={t.newFolder}
              />
              <button type="submit" disabled={isCreatingFolder || !newFolderName.trim()} title={t.create}>
                {isCreatingFolder ? <LoaderCircle className="spin" size={16} /> : <FolderPlus size={16} />}
              </button>
            </form>
            <div className="uploadList">
              <div className="uploadListHeader">
                <FolderOpen size={15} />
                <span>{t.uploads}</span>
              </div>
              {uploads.length > 0 ? (
                uploads.map((upload) => (
                  <button key={upload.id} type="button" className="uploadRecord" onClick={() => handleOpenUpload(upload)}>
                    <span>{upload.original_filename}</span>
                    <small>{upload.folder_name ?? t.folder}</small>
                  </button>
                ))
              ) : (
                <p className="emptyUploads">{t.noUploads}</p>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panelHeader">
              <ImageIcon size={18} />
              <h2>{t.samples}</h2>
            </div>
            <div className="sampleGrid">
              {samples.map((sample) => (
                <button
                  key={sample.name}
                  className={`sampleTile ${selectedSample?.name === sample.name ? "selected" : ""}`}
                  onClick={() => handleSampleSelect(sample)}
                  type="button"
                  title={sample.name}
                >
                  <img src={apiUrl(sample.url)} alt={sample.name} />
                  <span>{SAMPLE_HINTS[language][sample.name] ?? sample.name}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="panel">
            <div className="panelHeader">
              <Settings2 size={18} />
              <h2>{t.traceStyle}</h2>
            </div>
            <div className="styleList styleSwitcher" role="tablist" aria-label={t.traceStyleAria}>
              {visibleStyles.map((style) => (
                <button
                  key={style.id}
                  className={`styleOption ${settings.styleId === style.id ? "selected" : ""}`}
                  onClick={() => handleStyleChange(style.id)}
                  type="button"
                  role="tab"
                  aria-selected={settings.styleId === style.id}
                >
                  <span>{style.name}</span>
                  <small>{style.summary}</small>
                </button>
              ))}
            </div>
          </section>

          <section className="panel">
            <div className="panelHeader">
              <Gauge size={18} />
              <h2>{t.processing}</h2>
            </div>
            <SliderControl
              label={t.sensitivity}
              min={0.05}
              max={0.95}
              step={0.01}
              value={settings.sensitivity}
              format={(value) => `${Math.round(value * 100)}%`}
              onChange={(value) => setSettings((current) => ({ ...current, sensitivity: value }))}
            />
            <SliderControl
              label={t.noiseFilter}
              min={0}
              max={10}
              step={1}
              value={settings.noiseFilter}
              format={(value) => `${value}`}
              onChange={(value) => setSettings((current) => ({ ...current, noiseFilter: value }))}
            />
            <SliderControl
              label={t.simplify}
              min={0}
              max={8}
              step={0.1}
              value={settings.simplifyTolerance}
              format={(value) => `${value.toFixed(1)} px`}
              onChange={(value) => setSettings((current) => ({ ...current, simplifyTolerance: value }))}
            />
          </section>

          <section className="panel">
            <div className="panelHeader">
              <Ruler size={18} />
              <h2>{t.dxfScale}</h2>
            </div>
            <div className="numberGrid">
              <label>
                <span>{t.widthMm}</span>
                <input
                  type="number"
                  min="0"
                  value={settings.slabWidthMm}
                  onChange={(event) =>
                    setSettings((current) => ({ ...current, slabWidthMm: Number(event.target.value) }))
                  }
                />
              </label>
              <label>
                <span>{t.heightMm}</span>
                <input
                  type="number"
                  min="0"
                  value={settings.slabHeightMm}
                  onChange={(event) =>
                    setSettings((current) => ({ ...current, slabHeightMm: Number(event.target.value) }))
                  }
                />
              </label>
            </div>
          </section>

          <div className="actionStack">
            <button
              className="primaryButton"
              type="button"
              onClick={handleProcess}
              disabled={(!selectedFile && !selectedSample) || isProcessing || isLoading}
            >
              {isProcessing ? <LoaderCircle className="spin" size={18} /> : <Wand2 size={18} />}
              {isProcessing ? t.tracing : t.traceImage}
            </button>
            <button className="ghostButton" type="button" onClick={resetWorkspace}>
              <RefreshCcw size={17} />
              {t.reset}
            </button>
          </div>
        </aside>

        <section className="previewDeck">
          {error && (
            <div className="alert" role="alert">
              <CircleAlert size={18} />
              <span>{error}</span>
            </div>
          )}

          <div className="outputGrid">
            <div className="canvasPanel">
              <div className="canvasHeader">
                <div>
                  <h2>{modifiedPreviewUrl ? t.revisedPreview : (activeStyle?.name ?? t.preview)}</h2>
                  <p>{selectedFile?.name ?? selectedSample?.name ?? t.noImage}</p>
                </div>
                <div className="tabs" role="tablist" aria-label={t.previewTypeAria}>
                  <button
                    className={previewMode === "preview" ? "active" : ""}
                    type="button"
                    onClick={() => setPreviewMode("preview")}
                    disabled={!result}
                  >
                    {t.preview}
                  </button>
                  <button
                    className={previewMode === "mask" ? "active" : ""}
                    type="button"
                    onClick={() => setPreviewMode("mask")}
                    disabled={!result}
                  >
                    {t.mask}
                  </button>
                </div>
              </div>

              <div className="previewFrame">
                {previewUrl ? (
                  <img src={previewUrl} alt={`${previewMode} ${t.resultAlt}`} />
                ) : sourcePreviewUrl ? (
                  <img src={sourcePreviewUrl} alt={t.sourceWaitingAlt} />
                ) : (
                  <div className="emptyState">
                    <UploadCloud size={42} />
                    <span>{t.selectImage}</span>
                  </div>
                )}
              </div>
            </div>

          </div>

          <section className="resultBand">
            <MetricCard label={t.lines} value={result ? result.metrics.line_count.toLocaleString() : "0"} />
            <MetricCard
              label={t.length}
              value={result ? `${Math.round(result.metrics.total_length_mm).toLocaleString()} mm` : "0 mm"}
            />
            <MetricCard
              label={t.scale}
              value={result ? `${result.metrics.mm_per_pixel.toFixed(3)} mm/px` : t.pending}
            />
            <MetricCard label={t.time} value={result ? `${result.metrics.processing_ms} ms` : t.pending} />
          </section>

          <section className="exportPanel">
            <div className="exportCopy">
              <BadgeCheck size={20} />
              <div>
                <h2>{modifiedDxfUrl ? t.revisedDxfReady : result ? t.dxfReady : t.dxfOutput}</h2>
                <p>
                  {result
                    ? result.metrics.scale_confirmed
                      ? `${t.workArea} ${result.metrics.width_px} x ${result.metrics.height_px} px`
                      : t.scaleIsOne
                    : t.traceToCreate}
                </p>
              </div>
            </div>
            <a
              className={`downloadButton ${dxfDownloadUrl ? "" : "disabled"}`}
              href={dxfDownloadUrl ? apiUrl(dxfDownloadUrl) : undefined}
              aria-disabled={!dxfDownloadUrl}
            >
              <Download size={18} />
                {t.downloadDxf}
            </a>
          </section>

          <div className="apiNote">
            <span>{t.backend}</span>
            <code>{API_BASE_URL}</code>
          </div>
        </section>
      </section>

      {isChatOpen && (
        <section className="chatPanel floatingChatPanel" id="cad-chat-panel" aria-label={t.cadChat}>
          <div className="chatTitleBar">
            <div className="panelHeader">
              <MessageSquare size={18} />
              <h2>{t.cadChat}</h2>
            </div>
            <button
              className="chatCloseButton"
              type="button"
              onClick={() => setIsChatOpen(false)}
              aria-label={t.closeCadChat}
              title={t.closeCadChat}
            >
              <X size={17} />
            </button>
          </div>
          <div className="chatMessages" aria-live="polite">
            {chatMessages.length > 0 ? (
              chatMessages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={`chatBubble ${message.role}`}>
                  <span>{message.role === "user" ? t.you : t.cadAssistant}</span>
                  <p>{message.content}</p>
                </div>
              ))
            ) : (
              <div className="chatEmpty">
                <MessageSquare size={30} />
                <p>{t.chatEmpty}</p>
              </div>
            )}
          </div>
          <form className="chatForm" onSubmit={handleDxfChat}>
            <input
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder={t.chatPlaceholder}
              disabled={isChatting}
            />
            <button type="submit" disabled={!chatInput.trim() || isChatting} title={t.sendCadEdit}>
              {isChatting ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}
            </button>
          </form>
        </section>
      )}

      <button
        className={`chatFab ${isChatOpen ? "active" : ""}`}
        type="button"
        onClick={() => setIsChatOpen((current) => !current)}
        aria-expanded={isChatOpen}
        aria-controls="cad-chat-panel"
        aria-label={isChatOpen ? t.closeCadChat : t.openCadChat}
        title={isChatOpen ? t.closeCadChat : t.openCadChat}
      >
        <MessageSquare size={22} />
        {chatMessages.length > 0 && <span className="chatFabBadge">{Math.min(chatMessages.length, 99)}</span>}
      </button>
    </main>
  );
}

function SliderControl({
  label,
  min,
  max,
  step,
  value,
  format,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  format: (value: number) => string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="sliderControl">
      <span>
        {label}
        <strong>{format(value)}</strong>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="metricCard">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
