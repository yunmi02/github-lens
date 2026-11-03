export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> =
    options.body instanceof FormData
      ? {}
      : { "Content-Type": "application/json" };
  const credential = sessionStorage.getItem("uploadCredential");
  if (location.pathname === "/mobile" && credential)
    headers["X-Upload-Credential"] = credential;
  const response = await fetch("/api" + path, {
    ...options,
    headers: { ...headers, ...options.headers },
    credentials: "same-origin",
  });
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {
      data = { detail: response.status === 413 ? "请求过大，单张图片不能超过 20 MB" : "服务暂时不可用" };
    }
    const message =
      typeof data.detail === "string"
        ? data.detail
        : "输入不符合要求，请检查后重试";
    throw new Error(message);
  }
  return response.json();
}

export type Claim = { text: string; quote: string; source: string };
export type Project = {
  id: number;
  full_name: string;
  description: string;
  display_description?: string;
  categories?: string[];
  category_labels?: string[];
  keywords?: string[];
  classification_method?: string;
  category_options?: { id: string; label: string }[];
  summary_health?: { complete: boolean; overview_zh: boolean; verified_count: number; missing_fields: string[] };
  summary_task?: { job_id: string; status: string; stage: string; error?: string } | null;
  language: string;
  stars: number;
  forks: number;
  favorite: boolean;
  collected: boolean;
  archived: boolean;
  tags: string[];
  notes: string;
  study_status: string;
  trashed_at?: string | null;
  fetched_at: string;
  metadata: any;
  summary: any;
  readme?: string;
  research_provider?: string;
  research_task?: { job_id: string; status: string; stage: string; error: string; prompt: string } | null;
  images?: { id: string; filename: string }[];
  snapshots?: { date: string; stars: number }[];
};
export type ImageItem = {
  id: string;
  filename: string;
  status: string;
  error: string;
  text: string;
  candidates: any[];
  research?: { status: string; stage: string; error: string } | null;
};
export type Batch = {
  id: string;
  source: string;
  created_at: string;
  images: ImageItem[];
};
export const date = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date(value))
    : "未提供";
export const num = (value: number) =>
  new Intl.NumberFormat("zh-CN", {
    notation: value >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
export const safeLink = (value: string) =>
  /^https?:\/\//i.test(value || "") ? value : "#";
