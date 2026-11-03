import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Compass,
  ExternalLink,
  FileImage,
  FolderOpen,
  Github,
  LayoutDashboard,
  LayoutGrid,
  List,
  LoaderCircle,
  LogOut,
  Plus,
  QrCode,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Star,
  Tag,
  Trash2,
  Upload,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import {
  api,
  Batch,
  Claim,
  date,
  ImageItem,
  num,
  Project,
  safeLink,
} from "./api";
import "./styles.css";
import "./research.css";
import "./archive.css";
import "./project-library.css";
import ResearchPanel from "./ResearchPanel";
import GitHubTokenForm from "./GitHubTokenForm";
import PasswordForm from "./PasswordForm";
import ComputerUseStatus, { browserTaskActive } from "./ComputerUseStatus";

type View =
  "overview" | "projects" | "imports" | "discover" | "settings" | "jobs";
type Notice = (text: string, error?: boolean) => void;
const statusText: Record<string, string> = {
  queued: "等待处理",
  recognizing: "识别中",
  researching: "智能研究中",
  collecting: "关联处理中",
  running: "处理中",
  needs_review: "待确认",
  completed: "已完成",
  failed: "失败",
  ignored: "已忽略",
  waiting_browser: "等待浏览器检索",
  browser_running: "浏览器检索中",
  cancelled: "已取消",
};
const navs = [
  { id: "overview", label: "工作台", icon: LayoutDashboard },
  { id: "projects", label: "我的项目", icon: BookOpen },
  { id: "imports", label: "截图导入", icon: FileImage },
  { id: "discover", label: "发现项目", icon: Compass },
  { id: "jobs", label: "任务中心", icon: Clock3 },
] as const;

function App() {
  const initialLocation = new URLSearchParams(location.search);
  const initialView = initialLocation.get("view") as View;
  const [auth, setAuth] = useState<any>(null),
    [view, setView] = useState<View>(["overview", "projects", "imports", "discover", "settings", "jobs"].includes(initialView) ? initialView : "overview"),
    [stats, setStats] = useState<any>({}),
    [selected, setSelected] = useState<number | null>(() => { const id = Number(initialLocation.get("project")); return Number.isSafeInteger(id) && id > 0 ? id : null; }),
    [toast, setToast] = useState<{ text: string; error: boolean } | null>(null),
    [tick, setTick] = useState(0),
    [qr, setQr] = useState(false),
    [link, setLink] = useState(false);
  const notice: Notice = (text, error = false) => setToast({ text, error });
  const reload = () => setTick((t) => t + 1);
  useEffect(() => {
    if (location.pathname === "/mobile") return;
    const params = new URLSearchParams(location.search);
    params.set("view", view);
    if (selected) params.set("project", String(selected)); else params.delete("project");
    history.replaceState(null, "", `${location.pathname}?${params}`);
  }, [view, selected]);
  useEffect(() => {
    api("/auth/status")
      .then(setAuth)
      .catch((e) => notice(e.message, true));
  }, []);
  useEffect(() => {
    if (!auth?.authenticated) return;
    const update = () =>
      api("/stats")
        .then(setStats)
        .catch(() => {});
    update();
    const id = setInterval(update, 5000);
    return () => clearInterval(id);
  }, [auth, tick]);
  useEffect(() => {
    if (toast) {
      const id = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(id);
    }
  }, [toast]);
  if (location.pathname === "/mobile") return <Mobile />;
  if (!auth)
    return (
      <div className="loading-page">
        <LoaderCircle className="spin" />
        正在连接资料库…{toast && <p className="error-text">{toast.text}</p>}
      </div>
    );
  if (!auth.authenticated)
    return (
      <Login
        setup={auth.setup_required}
        onLogin={() =>
          setAuth({ ...auth, authenticated: true, setup_required: false })
        }
      />
    );
  return (
    <div className="app">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView("overview");
            setSelected(null);
          }}
        >
          <span className="brand-icon">
            <Github size={23} />
          </span>
          <span>
            GitHub Lens<small>你的项目情报库</small>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-avatar">我</span>
          <div>
            个人工作空间<small>开源项目资料库</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-label">工作空间</div>
        <nav>
          {navs.map((n) => (
            <button
              key={n.id}
              aria-label={n.label}
              className={view === n.id ? "active" : ""}
              onClick={() => {
                setView(n.id);
                setSelected(null);
              }}
            >
              <n.icon size={19} />
              {n.label}
              {n.id === "imports" && stats.needs_review > 0 && (
                <span className="nav-count">{stats.needs_review}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-tip">
          <div className="tip-icon">
            <QrCode size={21} />
          </div>
          <b>灵感，随手收集</b>
          <p>
            手机截图扫码上传，
            <br />
            让好项目不再被遗忘。
          </p>
          <button onClick={() => setQr(true)}>
            连接手机 <ArrowUpRight size={15} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <button
            onClick={() => {
              setView("settings");
              setSelected(null);
            }}
          >
            <Settings2 size={18} />
            偏好设置
          </button>
          <button
            onClick={async () => {
              await api("/auth/logout", { method: "POST" });
              setAuth({ ...auth, authenticated: false });
            }}
          >
            <LogOut size={18} />
            退出登录
          </button>
          <div className="version">
            本地工作空间 <span>v0.1.0</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            工作空间 <span>/</span>{" "}
            {selected
              ? "项目详情"
              : navs.find((n) => n.id === view)?.label || "偏好设置"}
          </div>
          <div className="top-actions">
            <span className="private-badge">
              <ShieldCheck size={14} />
              个人资料库
            </span>
            <button
              className="icon-btn"
              aria-label="查看任务"
              onClick={() => {
                setView("jobs");
                setSelected(null);
              }}
            >
              <Bell size={18} />
              {stats.pending > 0 && <span className="task-count">{stats.pending}</span>}
            </button>
            <span className="user-avatar">Y</span>
          </div>
        </header>
        <main className={selected ? "screen-detail" : `screen-${view}`}>
          {selected ? (
            <Detail
              id={selected}
              onBack={() => setSelected(null)}
              notice={notice}
              onUpdate={reload}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <h1>
                    {
                      {
                        overview: "从截图，到下一次灵感",
                        projects: "我的项目",
                        imports: "截图导入",
                        discover: "发现值得关注的项目",
                        settings: "偏好设置",
                        jobs: "任务中心",
                      }[view]
                    }
                  </h1>
                  <p>
                    {
                      {
                        overview:
                          "收集偶然遇见的好项目，把碎片信息变成可用的知识。",
                        projects:
                          "让收藏有条理，让每一个好项目都能被再次找到。",
                        imports: "上传截图，自动识别仓库并整理项目资料。",
                        discover:
                          "从 GitHub 近期新项目中，寻找下一个值得研究的工具。",
                        settings: "管理识别服务、自动发现与个人工作空间。",
                        jobs: "查看识别、资料补全和自动发现的处理状态。",
                      }[view]
                    }
                  </p>
                </div>
                <div className="heading-actions">
                  {view !== "settings" && view !== "jobs" && (
                    <>
                      <button
                        className="btn secondary"
                        onClick={() => setQr(true)}
                      >
                        <QrCode size={17} />
                        手机上传
                      </button>
                      <button
                        className="btn primary"
                        onClick={() => setLink(true)}
                      >
                        <Plus size={17} />
                        添加项目
                      </button>
                    </>
                  )}
                </div>
              </div>
              {view === "overview" && (
                <Overview
                  stats={stats}
                  onView={setView}
                  onSelect={setSelected}
                  notice={notice}
                  tick={tick}
                  onChange={reload}
                />
              )}
              {view === "projects" && (
                <Projects onSelect={setSelected} notice={notice} tick={tick} onUpdate={reload} />
              )}
              {view === "imports" && (
                <Imports
                  notice={notice}
                  onChange={reload}
                  onSelect={setSelected}
                />
              )}
              {view === "discover" && (
                <Discover
                  notice={notice}
                  onSelect={setSelected}
                  onChange={reload}
                />
              )}
              {view === "settings" && <Settings notice={notice} />}
              {view === "jobs" && <Jobs notice={notice} />}
            </>
          )}
        </main>
        <footer>
          为每一次发现，留一个位置。
          <span>GitHub Lens / 数据来源于 GitHub，摘要可追溯</span>
        </footer>
      </div>
      {qr && <PhoneModal onClose={() => setQr(false)} notice={notice} />}{" "}
      {link && (
        <LinkModal
          onClose={() => setLink(false)}
          notice={notice}
          onChange={reload}
        />
      )}{" "}
      {toast && (
        <div role="status" className={"toast " + (toast.error ? "bad" : "")}>
          {toast.error ? <XCircle size={18} /> : <CheckCircle2 size={18} />}{" "}
          {toast.text}
          <button aria-label="关闭提示" onClick={() => setToast(null)}>
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function Login({ setup, onLogin }: { setup: boolean; onLogin: () => void }) {
  const [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="brand">
          <span className="brand-icon">
            <Github />
          </span>
          <span>GitHub Lens</span>
        </div>
        <h1>
          好项目，
          <br />
          值得被记住。
        </h1>
        <p>
          从手机里的一张截图开始，
          <br />
          建立属于你的开源项目情报库。
        </p>
        <div className="login-diagram">
          <FileImage />
          <span>截图</span>
          <ArrowRight />
          <Sparkles />
          <span>理解</span>
          <ArrowRight />
          <BookOpen />
          <span>知识</span>
        </div>
      </div>
      <form
        className="login-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            await api(setup ? "/auth/setup" : "/auth/login", {
              method: "POST",
              body: JSON.stringify({ password }),
            });
            onLogin();
          } catch (e: any) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <span className="small-logo">
          <Github size={28} />
        </span>
        <h2>{setup ? "创建你的工作空间" : "欢迎回来"}</h2>
        <p>
          {setup
            ? "设置管理员密码，开始整理你的项目。"
            : "登录后继续探索你的开源收藏。"}
        </p>
        <label>
          管理员密码
          <input
            autoFocus
            autoComplete={setup ? "new-password" : "current-password"}
            type="password"
            minLength={10}
            maxLength={200}
            required
            placeholder="至少 10 个字符"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <p className="error-text">{error}</p>}
        <button className="btn primary" disabled={busy}>
          {busy ? (
            <LoaderCircle className="spin" size={17} />
          ) : (
            <ArrowRight size={17} />
          )}{" "}
          {setup ? "创建工作空间" : "登录工作空间"}
        </button>
        <small>
          <ShieldCheck size={14} />
          <span><abbr title="文字识别">OCR</abbr> 本地处理；智能研究会调用配置的 <abbr title="人工智能">AI</abbr> 服务。</span>
        </small>
      </form>
    </div>
  );
}

function Overview({ stats, onView, onSelect, notice, tick, onChange }: any) {
  const [items, setItems] = useState<Project[]>([]);
  useEffect(() => {
    const load = () =>
      api("/projects")
        .then((r) => setItems(r.items.slice(0, 6)))
        .catch((e: any) => notice(e.message, true));
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [tick]);
  return (
    <>
      <div className="overview-workbench">
      <div className="stat-grid">
        {[
          {
            label: "已收集项目",
            value: stats.projects,
            icon: BookOpen,
            sub: "每个发现，都有迹可循",
          },
          {
            label: "已导入截图",
            value: stats.images,
            icon: FileImage,
            sub: "碎片信息，集中管理",
          },
          {
            label: "特别关注",
            value: stats.favorites,
            icon: Star,
            sub: "留给下一次深入探索",
          },
          {
            label: "等待你确认",
            value: stats.needs_review,
            icon: Clock3,
            sub: "补充线索，让识别更准确",
          },
        ].map((s, i) => (
          <button
            className="stat"
            key={s.label}
            onClick={() => onView(i === 1 || i === 3 ? "imports" : "projects")}
          >
            <div>
              <span>{s.label}</span>
              <s.icon size={18} />
            </div>
            <strong>
              {s.value ?? "—"}
              <small>{i === 1 ? "张" : "个"}</small>
            </strong>
            <p>
              {s.sub}
            </p>
          </button>
        ))}
      </div>
      <section className="capture-panel">
        <div className="capture-copy">
          <h2>
            看见好项目，
            <br />
            剩下的交给 Lens。
          </h2>
          <p>
            识别截图中的 GitHub 项目，自动补全功能、
            <br />
            技术特色、版本信息和官方链接。
          </p>
          <div className="capture-steps">
            <span>01 上传截图</span>
            <ArrowRight size={13} />
            <span>02 识别与核对</span>
            <ArrowRight size={13} />
            <span>03 生成档案</span>
          </div>
        </div>
        <UploadBox
          notice={notice}
          onDone={() => {
            onChange();
            onView("imports");
          }}
          compact
        />
      </section>
      </div>
      <div className="section-heading">
        <div>
          <h2>
            最近收集 <span className="count">{stats.projects ?? 0}</span>
          </h2>
          <p>重新遇见那些让你眼前一亮的项目。</p>
        </div>
        <button className="text-btn" onClick={() => onView("projects")}>
          查看全部 <ArrowRight size={15} />
        </button>
      </div>
      {items.length ? (
        <div className="project-grid">
          {items.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              onSelect={onSelect}
              notice={notice}
              onChange={() =>
                setItems(
                  items.map((i) =>
                    i.id === p.id ? { ...i, favorite: !i.favorite } : i,
                  ),
                )
              }
            />
          ))}
        </div>
      ) : (
        <Empty
          icon={BookOpen}
          title="你的下一个好项目，从这里开始"
          text="上传第一张截图，或通过 GitHub 链接添加项目。"
        />
      )}
      <div className="discovery-banner">
        <div className="discovery-symbol">
          <Compass size={25} />
        </div>
        <div>
          <h3>让好项目主动找到你</h3>
          <p>设置关注领域，自动发现近期创建的高 Star 项目。</p>
        </div>
        <button className="btn secondary" onClick={() => onView("discover")}>
          开启探索 <ArrowUpRight size={16} />
        </button>
      </div>
    </>
  );
}

function UploadBox({
  notice,
  onDone,
  compact = false,
}: {
  notice: Notice;
  onDone: () => void;
  compact?: boolean;
}) {
  const files = useRef<HTMLInputElement>(null),
    folder = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false),
    [drag, setDrag] = useState(false),
    [progress, setProgress] = useState({ done: 0, total: 0 }),
    [errors, setErrors] = useState<string[]>([]);
  async function upload(list: FileList | File[] | null) {
    if (!list || busy) return;
    const all = Array.from(list),
      valid = all
        .filter((f) => /\.(png|jpe?g|webp)$/i.test(f.name))
        .slice(0, 100),
      skipped = all.length - valid.length;
    if (!valid.length) {
      notice("请选择 PNG、JPEG 或 WebP 图片", true);
      return;
    }
    setBusy(true);
    setProgress({ done: 0, total: valid.length });
    setErrors([]);
    const failures: string[] = [];
    try {
      const batch = await api("/import-batches", { method: "POST" });
      if (location.pathname === "/mobile") {
        sessionStorage.setItem("lastUploadBatch", batch.id);
        window.dispatchEvent(new Event("upload-batch-created"));
      }
      for (let i = 0; i < valid.length; i++) {
        const form = new FormData();
        form.append("file", valid[i]);
        try {
          await api(`/import-batches/${batch.id}/images`, {
            method: "POST",
            body: form,
          });
        } catch (e: any) {
          failures.push(`${valid[i].name}：${e.message}`);
        }
        setProgress({ done: i + 1, total: valid.length });
      }
      setErrors(failures);
      notice(
        `已接收 ${valid.length - failures.length} 张图片${skipped ? `，跳过 ${skipped} 个不支持或超额文件` : ""}`,
        !!failures.length,
      );
      if (!failures.length) onDone();
    } catch (e: any) {
      notice(e.message, true);
    } finally {
      setBusy(false);
      if (files.current) files.current.value = "";
      if (folder.current) folder.current.value = "";
    }
  }
  return (
    <div className={"upload-wrapper " + (compact ? "compact" : "")}>
      <div
        className={"upload-box " + (drag ? "drag" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          upload(e.dataTransfer.files);
        }}
      >
        <div className="upload-icon">
          {busy ? (
            <LoaderCircle className="spin" size={27} />
          ) : (
            <Upload size={27} />
          )}
        </div>
        <h3>
          {busy
            ? `正在上传 ${progress.done} / ${progress.total}`
            : "将项目截图拖到这里"}
        </h3>
        <p>支持单张、多张图片或整个文件夹</p>
        {busy ? (
          <div className="progress">
            <span
              style={{ width: `${(progress.done / progress.total) * 100}%` }}
            />
          </div>
        ) : (
          <div className="upload-buttons">
            <button
              className="btn primary"
              onClick={() => files.current?.click()}
            >
              <Plus size={16} />
              选择图片
            </button>
            <button
              className="btn secondary"
              onClick={() => folder.current?.click()}
            >
              <FolderOpen size={16} />
              选择文件夹
            </button>
          </div>
        )}
        <small><abbr title="支持的图片格式">PNG / JPG / WEBP</abbr>，单张 ≤ 20 MB，每批 ≤ 100 张</small>
        <small className="upload-agent-note">
          待处理图片可由智能体调用 AI 解析并联网搜索。
        </small>
        <input
          hidden
          ref={files}
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp"
          onChange={(e) => upload(e.target.files)}
        />
        <input
          hidden
          ref={folder}
          type="file"
          multiple
          {...({ webkitdirectory: "" } as any)}
          onChange={(e) => upload(e.target.files)}
        />
      </div>
      {errors.length > 0 && (
        <div className="upload-errors">
          <b>以下文件上传失败，可重新选择重试：</b>
          {errors.map((s) => (
            <p key={s}>{s}</p>
          ))}
          <button className="text-btn" onClick={onDone}>
            查看已上传图片 <ArrowRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

function ProjectCard({
  project: p,
  onSelect,
  notice,
  onChange,
  variant = "archive",
  onTrash,
  trashBusy = false,
}: {
  project: Project;
  onSelect: (id: number) => void;
  notice: Notice;
  onChange?: () => void;
  variant?: "archive" | "library";
  onTrash?: () => void;
  trashBusy?: boolean;
}) {
  const name = p.full_name.split("/");
  const [avatarFailed, setAvatarFailed] = useState(false);
  useEffect(() => setAvatarFailed(false), [p.full_name]);
  const tone = Array.from(p.full_name).reduce((hash, c) => ((hash * 31) + c.charCodeAt(0)) >>> 0, 0) % 6;
  const library = variant === "library";
  return (
    <article className={"project-card" + (library ? " library-card" : "") + (p.favorite ? " is-followed" : "")} data-tone={tone}>
      <div className="card-top">
        <span className="repo-avatar">
          {library && !avatarFailed ? <img src={`https://github.com/${encodeURIComponent(name[0])}.png?size=96`}
            alt="" width={56} height={56} loading="lazy" onError={() => setAvatarFailed(true)} /> : name[1]?.slice(0, 2).toUpperCase()}
        </span>
        {library && <div className="card-identity">
          <span className="project-language">{p.language || "未标注语言"}</span>
          {p.study_status && <span className="project-study" data-status={p.study_status}>{p.study_status}</span>}
        </div>}
        <div className={library ? "card-actions" : "archive-actions"}>
        <button
          className={"icon-btn favorite " + (p.favorite ? "is-favorite" : "")}
          aria-label={p.favorite ? "取消特别关注" : "特别关注"}
          onClick={async () => {
            try {
              await api(`/projects/${p.id}`, {
                method: "PATCH",
                body: JSON.stringify({ favorite: !p.favorite }),
              });
              onChange?.();
            } catch (e: any) {
              notice(e.message, true);
            }
          }}
        >
          <Star size={18} fill={p.favorite ? "currentColor" : "none"} />
          {library && p.favorite && <span>已关注</span>}
        </button>
        {library && onTrash && <button type="button" className="icon-btn card-trash"
          aria-label={`将 ${p.full_name} 移入回收站`} title="移入回收站" disabled={trashBusy} onClick={onTrash}>
          {trashBusy ? <LoaderCircle size={16} className="spin" /> : <Trash2 size={16} />}
        </button>}
        </div>
      </div>
      <button className="card-link" onClick={() => onSelect(p.id)}>
        <small>{name[0]}</small>
        <h3>
          {name[1]} <ArrowUpRight size={17} />
        </h3>
      </button>
      <p className="card-description">
        {p.display_description || p.summary?.overview?.text || p.description || "仓库尚未提供简介"}
      </p>
      {!!p.category_labels?.length && <div className="card-categories" aria-label="项目用途分类">{p.category_labels.map(label => <span key={label}>{label}</span>)}</div>}
      {variant === "library" && p.summary_health && <small className="card-summary-state">{p.summary_health.complete ? "中文资料已归纳" : "中文资料待补全"}</small>}
      <div className="card-tags">
        {(p.tags.length ? p.tags : p.metadata.topics || [])
          .slice(0, 3)
          .map((t: string) => (
            <span key={t}>{t}</span>
          ))}
      </div>
      <div className="card-bottom">
        <span>
          {p.language || "未标注"}
        </span>
        <span>
          <Star size={13} />
          {num(p.stars)}
        </span>
        <span className="card-date">{date(p.metadata.created_at)} 创建</span>
      </div>
    </article>
  );
}

function Projects({
  onSelect,
  notice,
  tick,
  onUpdate,
}: {
  onSelect: (id: number) => void;
  notice: Notice;
  tick: number;
  onUpdate?: () => void;
}) {
  const [q, setQ] = useState(""),
    [language, setLanguage] = useState(""),
    [favorite, setFavorite] = useState(false),
    [sort, setSort] = useState("recent"),
    [category, setCategory] = useState(""),
    [summaryState, setSummaryState] = useState(""),
    [page, setPage] = useState(1),
    [data, setData] = useState<any>({ items: [], total: 0, languages: [] }),
    [busy, setBusy] = useState(true),
    [localTick, setLocalTick] = useState(0),
    [inTrash, setInTrash] = useState(() => new URLSearchParams(location.search).get("trash") === "1"),
    [actionId, setActionId] = useState<number | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (inTrash) params.set("trash", "1"); else params.delete("trash");
    history.replaceState(null, "", `${location.pathname}?${params}`);
  }, [inTrash]);
  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    const t = setTimeout(
      () =>
        api(
          `/projects?q=${encodeURIComponent(q)}&language=${encodeURIComponent(language)}&favorite=${favorite}&sort=${sort}&page=${page}&trash=${inTrash}&category=${encodeURIComponent(category)}&summary_state=${summaryState}`,
        )
          .then(result => { if (!cancelled) setData(result); })
          .catch((e) => { if (!cancelled) notice(e.message, true); })
          .finally(() => { if (!cancelled) setBusy(false); }),
      200,
    );
    return () => { cancelled = true; clearTimeout(t); };
  }, [q, language, favorite, sort, page, tick, localTick, inTrash, category, summaryState]);
  const curationActive = ["queued", "running"].includes(data.curation_task?.status);
  useEffect(() => {
    if (!curationActive) return;
    const timer = setInterval(() => setLocalTick(t => t + 1), 4000);
    return () => clearInterval(timer);
  }, [curationActive]);
  async function moveProject(p: Project, restore = false) {
    setActionId(p.id);
    try {
      await api(`/projects/${p.id}${restore ? "/restore" : ""}`, { method: restore ? "POST" : "DELETE" });
      setData((old: any) => ({ ...old, items: old.items.filter((item: Project) => item.id !== p.id), total: Math.max(0, old.total - 1) }));
      if (page > 1 && data.items.length === 1) setPage(page - 1);
      setLocalTick(t => t + 1);
      onUpdate?.();
      notice(restore ? `${p.full_name} 已恢复到项目库` : `${p.full_name} 已移入回收站，可在回收站恢复`);
    } catch (e: any) { notice(e.message, true); }
    finally { setActionId(null); }
  }
  return (
    <>
      <div className="collection-tabs" role="tablist" aria-label="项目列表范围">
        <button role="tab" aria-selected={!inTrash} onClick={() => { setInTrash(false); setPage(1); setLanguage(""); setCategory(""); }}>
          <BookOpen size={16} />项目库{data.active_total != null && <span>{data.active_total}</span>}
        </button>
        <button role="tab" aria-selected={inTrash} onClick={() => { setInTrash(true); setPage(1); setLanguage(""); setCategory(""); }}>
          <Trash2 size={16} />回收站{data.trash_total != null && <span>{data.trash_total}</span>}
        </button>
      </div>
      {inTrash && <p className="trash-explanation">项目的笔记、标签和截图关联均已保留，可随时恢复。</p>}
      {!inTrash && <section className="library-organization" aria-label="资料整理与分类">
        <div className="library-organization-heading"><div><h2>按用途找到下一件工具</h2><p>搜索中文简介、功能、场景、关键词、标签和笔记；空格可组合多个关键词。</p></div>
          <button className="btn secondary small" disabled={curationActive} onClick={async () => {
            try { await api("/projects/curate", { method: "POST" }); setLocalTick(t => t + 1); notice("已安排中文资料补全与用途分类"); }
            catch (e: any) { notice(e.message, true); }
          }}><Sparkles size={15} />{curationActive ? "正在整理资料…" : "补全中文与分类"}</button></div>
        {data.curation_task && (curationActive || data.curation_task.error) && <p className="library-task" role="status">{data.curation_task.error || data.curation_task.stage}</p>}
        <div className="category-filters" aria-label="按用途筛选">
          <button aria-pressed={!category} onClick={() => { setCategory(""); setPage(1); }}>全部用途</button>
          {(data.categories || []).filter((c: any) => c.count > 0).map((c: any) => <button key={c.id} aria-pressed={category === c.id} onClick={() => { setCategory(category === c.id ? "" : c.id); setPage(1); }}>{c.label}<span>{c.count}</span></button>)}
        </div>
      </section>}
      <div className="filter-bar">
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label="搜索项目"
            placeholder="搜索用途、功能或关键词，如：论文 翻译…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSort(e.target.value ? "relevance" : "recent");
              setPage(1);
            }}
          />
        </div>
        <select
          aria-label="筛选语言"
          value={language}
          onChange={(e) => {
            setLanguage(e.target.value);
            setPage(1);
          }}
        >
          <option value="">全部语言</option>
          {data.languages.map((l: string) => (
            <option key={l}>{l}</option>
          ))}
        </select>
        <button
          className={"btn secondary " + (favorite ? "selected" : "")}
          onClick={() => {
            setFavorite(!favorite);
            setPage(1);
          }}
        >
          <Star size={16} />
          特别关注
        </button>
        <select
          aria-label="项目排序"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          {q && <option value="relevance">相关程度</option>}
          <option value="recent">{inTrash ? "最近移入" : "最近更新"}</option>
          <option value="stars">Star 最多</option>
        </select>
      </div>
      {!inTrash && <div className="library-summary-filter"><label>中文资料 <select aria-label="筛选中文归纳状态" value={summaryState} onChange={e => { setSummaryState(e.target.value); setPage(1); }}><option value="">全部状态</option><option value="complete">已归纳</option><option value="pending">待补全</option></select></label><span>项目可属于多个用途分类，分类可在详情中调整。</span></div>}
      <div className="list-meta">
        共 {data.total} 个项目{" "}
        <span>
          {inTrash ? <Trash2 size={15} /> : <LayoutGrid size={15} />}
          {inTrash ? "可恢复项目" : "卡片视图"}
        </span>
      </div>
      {busy ? (
        <Loading />
      ) : data.items.length && inTrash ? (
        <div className="trash-list">{data.items.map((p: Project) => (
          <article className="trash-row" key={p.id}>
            <Trash2 size={20} aria-hidden="true" />
            <div><h3>{p.full_name}</h3><p>{p.summary?.overview?.text || p.description || "仓库尚未提供简介"}</p>
              <small>移入时间：{date(p.trashed_at || undefined)}</small></div>
            <button className="btn secondary" disabled={actionId === p.id} onClick={() => moveProject(p, true)}>
              <RefreshCw size={15} />恢复项目</button>
          </article>
        ))}</div>
      ) : data.items.length ? (
        <div className="project-grid">
          {data.items.map((p: Project) => (
            <ProjectCard
              key={p.id}
              project={p}
              variant="library"
              onTrash={() => moveProject(p)}
              trashBusy={actionId === p.id}
              onSelect={onSelect}
              notice={notice}
              onChange={() => setLocalTick((t) => t + 1)}
            />
          ))}
        </div>
      ) : (
        <Empty
          icon={inTrash ? Trash2 : Search}
          title={q ? "没有找到匹配的项目" : inTrash ? "回收站为空" : "资料库还在等待第一个发现"}
          text={inTrash ? "移入回收站的项目会显示在这里，也可以恢复到项目库。" : "试试其他筛选条件，或上传截图添加项目。"}
        />
      )}
      <div className="pagination">
        <button
          className="btn secondary"
          disabled={page === 1}
          onClick={() => setPage(page - 1)}
        >
          上一页
        </button>
        <span>第 {page} 页</span>
        <button
          className="btn secondary"
          disabled={page * 24 >= data.total}
          onClick={() => setPage(page + 1)}
        >
          下一页
        </button>
      </div>
    </>
  );
}

function Imports({
  notice,
  onChange,
  onSelect,
}: {
  notice: Notice;
  onChange: () => void;
  onSelect: (id: number) => void;
}) {
  const [batches, setBatches] = useState<Batch[]>([]),
    [filter, setFilter] = useState("all"),
    [review, setReview] = useState<ImageItem | null>(null);
  const load = () =>
    api("/import-batches")
      .then(setBatches)
      .catch((e) => notice(e.message, true));
  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, []);
  const all = batches.flatMap((b) => b.images),
    reviewCount = all.filter((i) =>
      ["needs_review", "failed", "researching"].includes(i.status),
    ).length;
  return (
    <>
      <UploadBox
        notice={notice}
        onDone={() => {
          load();
          onChange();
        }}
      />
      <div className="research-banner">
        <div>
          <h3><CheckCircle2 size={18} />自动确认与补全智能体</h3>
          <p>处理全部待确认图片，使用浏览器核对所有项目，再保存详情与来源。后台浏览器模式会自动执行。</p>
        </div>
        <button className="btn primary" disabled={!reviewCount} onClick={async () => {
          try {
            const result = await api("/auto-confirm-pending", { method: "POST" });
            notice(result.count ? `已安排 ${result.count} 张图片自动确认与补全` : "暂无可提交图片，可能已在处理中");
            load(); onChange();
          } catch (e: any) { notice(e.message, true); }
        }}><CheckCircle2 size={16} />自动处理全部待确认</button>
      </div>
      <div className="research-banner">
        <div>
          <h3>
            <Sparkles size={18} />
            让智能体接手待处理图片
          </h3>
          <p>
            读取图片线索、联网搜索并核实项目详情；每次最多处理 20
            张。由配置的浏览器执行器完成检索。
          </p>
        </div>
        <button
          className="btn primary"
          disabled={!reviewCount}
          onClick={async () => {
            try {
              const result = await api("/research-pending", { method: "POST" });
              notice(
                result.count
                  ? `已安排智能体研究 ${result.count} 张图片`
                  : "暂无可提交的图片，可能已在研究中",
              );
              load();
              onChange();
            } catch (e: any) {
              notice(e.message, true);
            }
          }}
        >
          <Sparkles size={16} />
          研究全部待处理
        </button>
      </div>
      <div className="section-heading">
        <div>
          <h2>导入记录</h2>
          <p>每张截图都保留来源，识别有疑问时由你来确认。</p>
        </div>
        <div className="segmented">
          <button
            className={filter === "all" ? "active" : ""}
            onClick={() => setFilter("all")}
          >
            全部
          </button>
          <button
            className={filter === "review" ? "active" : ""}
            onClick={() => setFilter("review")}
          >
            待处理 {reviewCount > 0 && `(${reviewCount})`}
          </button>
        </div>
      </div>
      {!batches.length && (
        <Empty
          icon={FileImage}
          title="还没有导入截图"
          text="支持手机截屏、项目介绍长图和 GitHub 页面截图。"
        />
      )}
      {batches.map((b) => {
        const images = b.images.filter(
          (i) =>
            filter === "all" ||
            ["needs_review", "failed", "researching"].includes(i.status),
        );
        if (filter === "review" && !images.length) return null;
        return (
          <section className="batch" key={b.id}>
            <div className="batch-heading">
              <span>
                {b.source === "phone" ? "手机上传" : "电脑导入"}{" "}
                <small>
                  {date(b.created_at)} / {b.images.length} 张
                </small>
              </span>
              <button
                className="icon-btn"
                aria-label="删除整个批次及原图"
                onClick={async () => {
                  if (
                    !window.confirm(
                      "删除此批次的原图和识别文字？已收集的公开项目信息将保留。",
                    )
                  )
                    return;
                  try {
                    await api(`/import-batches/${b.id}`, { method: "DELETE" });
                    load();
                    onChange();
                    notice("批次已删除");
                  } catch (e: any) {
                    notice(e.message, true);
                  }
                }}
              >
                <Trash2 size={15} />
              </button>
            </div>
            {images.map((i) => (
              <div className="image-row" key={i.id}>
                <img src={`/api/images/${i.id}/file`} alt={i.filename} />
                <div className="image-description">
                  <b>{i.filename}</b>
                  <p>
                    {(i.status === "completed"
                      ? i.candidates.filter((c) => c.confirmed).map((c) => c.full_name).join(" / ")
                      : i.status === "collecting" ? "正在获取项目资料并保存关联" : i.research?.stage) ||
                      i.error ||
                      i.candidates.map((c) => c.full_name).join(" / ") ||
                      "正在从截图中提取项目线索"}
                  </p>
                </div>
                <span className={"status status-" + i.status}>
                  {statusText[i.status]}
                </span>
                <button
                  className="btn secondary small"
                  onClick={() => setReview(i)}
                >
                  {["needs_review", "failed", "researching"].includes(i.status)
                    ? "确认项目"
                    : "查看详情"}
                  <ArrowRight size={13} />
                </button>
              </div>
            ))}
          </section>
        );
      })}
      {review && (
        <ReviewModal
          image={review}
          onSelect={(id) => {
            setReview(null);
            onSelect(id);
          }}
          onClose={() => setReview(null)}
          notice={notice}
          onChange={() => {
            load();
            onChange();
          }}
        />
      )}
    </>
  );
}

function ReviewModal({
  image: initialImage,
  onClose,
  notice,
  onChange,
  onSelect,
}: {
  image: ImageItem;
  onClose: () => void;
  notice: Notice;
  onChange: () => void;
  onSelect: (id: number) => void;
}) {
  const [image, setImage] = useState(initialImage);
  const researching = image.status === "researching";
  const [name, setName] = useState(""),
    [busy, setBusy] = useState(false);
  const confirm = async (full_name: string) => {
    setBusy(true);
    try {
      await api(`/recognitions/${image.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ full_name }),
      });
      notice("正在关联项目，成功后将移出待确认列表");
      onChange();
      onClose();
    } catch (e: any) {
      notice(e.message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="确认截图中的项目" onClose={onClose} wide>
      <div className="review-layout">
        <div className="review-image">
          <img src={`/api/images/${image.id}/file`} alt="原始截图" />
        </div>
        <div>
          <ResearchPanel
            image={image}
            onImage={setImage}
            onSelect={onSelect}
            notice={notice}
          />
          <p className="muted">
            {image.error ||
              "核对原始截图与候选仓库，也可以直接填写正确的 GitHub 链接。"}
          </p>
          {image.candidates.map((c) => (
            <div className="candidate" key={c.full_name}>
              <a
                href={`https://github.com/${c.full_name}`}
                target="_blank"
                rel="noreferrer"
              >
                {c.full_name}
                <ExternalLink size={13} />
              </a>
              <p>{c.evidence}</p>
              {c.description && <small>{c.description}</small>}
              {c.confirmation_error && <p className="error-text">{c.confirmation_error}</p>}
              <button
                disabled={busy || researching || image.status === "collecting" || c.confirmed}
                className="btn secondary small"
                onClick={() => confirm(c.full_name)}
              >
                {c.confirmed ? "已关联" : "确认此项目"}
              </button>
            </div>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              confirm(name);
            }}
          >
            <label>
              补充项目链接
              <input
                required
                placeholder="https://github.com/owner/repo"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button className="btn primary" disabled={busy || researching || image.status === "collecting"}>
              补全并关联
            </button>
          </form>
          <details>
            <summary>查看识别原文</summary>
            <pre className="ocr-text">{image.text || "尚无识别文字"}</pre>
          </details>
          <button
            className="text-btn muted"
            disabled={researching || image.status === "collecting"}
            onClick={async () => {
              try {
                await api(`/recognitions/${image.id}/ignore`, {
                  method: "POST",
                });
                onChange();
                onClose();
              } catch (e: any) {
                notice(e.message, true);
              }
            }}
          >
            忽略其余未确认项目
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Detail({
  id,
  onBack,
  notice,
  onUpdate,
}: {
  id: number;
  onBack: () => void;
  notice: Notice;
  onUpdate: () => void;
}) {
  const [p, setP] = useState<Project | null>(null),
    [notes, setNotes] = useState(""),
    [tags, setTags] = useState(""),
    [keywords, setKeywords] = useState(""),
    [busy, setBusy] = useState(false);
  const draftOwner = useRef<number | null>(null);
  const load = () =>
    api<Project>(`/projects/${id}`)
      .then((p) => {
        setP(p);
        if (draftOwner.current !== p.id) {
          setNotes(p.notes);
          setTags(p.tags.join(", "));
          setKeywords((p.keywords || []).join(", "));
          draftOwner.current = p.id;
        }
      })
      .catch((e) => notice(e.message, true));
  useEffect(() => {
    load();
  }, [id]);
  useEffect(() => {
    if (!browserTaskActive(p?.research_task?.status) && !["queued", "running"].includes(p?.summary_task?.status || "")) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [id, p?.research_task?.status, p?.summary_task?.status]);
  if (!p) return <Loading />;
  if (p.trashed_at) return <section className="panel trashed-detail">
    <Trash2 size={24} aria-hidden="true" /><h1>项目已移入回收站</h1>
    <p>{p.full_name}</p><p className="muted">笔记、标签和截图关联均已保留，恢复后可以继续查看与整理。</p>
    <div className="heading-actions"><button className="btn secondary" onClick={onBack}>返回项目列表</button>
      <button className="btn primary" disabled={busy} onClick={async () => {
        setBusy(true);
        try { await api(`/projects/${id}/restore`, { method: "POST" }); await load(); onUpdate(); notice("项目已恢复"); }
        catch (e: any) { notice(e.message, true); }
        finally { setBusy(false); }
      }}><RefreshCw size={15} />恢复项目</button></div>
  </section>;
  const meta = p.metadata,
    summary = p.summary || {};
  const chineseClaims = (items?: Claim[]) => !p.summary_health ? items : items?.filter(c => {
    const chinese = (c.text.match(/[\u3400-\u9fff]/g) || []).length;
    return chinese >= 2 && chinese / Math.max(1, (c.text.match(/[A-Za-z\u3400-\u9fff]/g) || []).length) >= 0.1;
  });
  async function patch(body: any) {
    const previous = p;
    setP({ ...p, ...body });
    try {
      const updated = await api(`/projects/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setP(current => current ? { ...current, ...updated } : current);
      onUpdate();
      notice("已保存");
    } catch (e: any) {
      setP(previous);
      notice(e.message, true);
    }
  }
  return (
    <>
      <button className="text-btn back" onClick={onBack}>
        <ArrowLeft size={16} />
        返回项目列表
      </button>
      <div className="detail-heading">
        <div className="detail-title">
          <span className="repo-avatar large">
            {p.full_name.split("/")[1]?.slice(0, 2).toUpperCase()}
          </span>
          <div>
            <span className="repository-owner">{p.full_name.split("/")[0]}</span>
            <h1>
              {p.full_name.split("/")[1]}
              {p.archived && <span className="status">已归档</span>}
            </h1>
            <p>{p.display_description || summary.overview?.text || p.description}</p>
          </div>
        </div>
        <div className="heading-actions">
          <button
            className="btn secondary"
            onClick={() => patch({ favorite: !p.favorite })}
          >
            <Star size={16} fill={p.favorite ? "currentColor" : "none"} />
            {p.favorite ? "已关注" : "特别关注"}
          </button>
          <a
            className="btn primary"
            href={safeLink(meta.html_url)}
            target="_blank"
            rel="noreferrer"
          >
            <Github size={17} />
            打开 GitHub
            <ArrowUpRight size={16} />
          </a>
        </div>
      </div>
      <div className="detail-stats">
        <span>
          <Star size={17} />
          <b>{num(p.stars)}</b> Star
        </span>
        <span>
          <Github size={17} />
          <b>{num(p.forks)}</b> Fork
        </span>
        <span>
          {p.language || "未标注语言"}
        </span>
        <span>
          <ShieldCheck size={16} />
          {meta.license?.spdx_id && meta.license.spdx_id !== "NOASSERTION" ? meta.license.spdx_id : "未识别许可证"}
        </span>
      </div>
      <div className="detail-columns">
        <div>
          <section className="panel">
            <div className="panel-heading">
              <h2>
                <Sparkles size={18} />
                项目解读
              </h2>
              <span className="pill">
                {summary.mode === "browser" ? "浏览器核对" : summary.mode === "computer_use" ? "computer-use 核对" : summary.mode === "ai" ? "AI 中文归纳" : "官方文档摘录"}
              </span>
            </div>
            <p className="overview-text">
              {(p.summary_health ? p.display_description : summary.overview?.text) ||
                p.description ||
                "请收藏项目以生成完整档案。"}
            </p>
            <p className="info-note">
              <CircleHelp size={15} />
              {summary.notice || "点击收藏后获取 README 与详细资料。"}
            </p>
            {summary.source_excerpt_fields?.length > 0 && <p className="muted">尚未归纳的内容可在下方 <abbr title="仓库说明文档">README</abbr> 官方原文中查看。</p>}
            {summary.curation_notice && <p className="muted">{summary.curation_notice}</p>}
            <div className="summary-curation-actions"><button className="btn primary small" disabled={busy || ["queued", "running"].includes(p.summary_task?.status || "")} onClick={async () => {
              setBusy(true);
              try { await api(`/projects/${id}/curate`, { method: "POST" }); await load(); notice("已安排智能体根据已有来源补全中文归纳"); }
              catch (e: any) { notice(e.message, true); }
              finally { setBusy(false); }
            }}><Sparkles size={15} />{["queued", "running"].includes(p.summary_task?.status || "") ? "正在整理中文资料…" : "补全中文归纳"}</button>
              {p.summary_task && (["queued", "running"].includes(p.summary_task.status) || p.summary_task.error) && <span role="status">{p.summary_task.error || p.summary_task.stage}</span>}</div>
            {["computer_use", "browser"].includes(p.research_provider || "") && <>
              <button className="btn secondary small" disabled={busy || browserTaskActive(p.research_task?.status)} onClick={async () => {
                setBusy(true);
                try { await api(`/projects/${id}/refresh`, { method: "POST" }); await load(); notice(p.research_provider === "browser" ? "已加入后台浏览器检索队列" : "已派发 computer-use 详情补全任务"); }
                catch (e: any) { notice(e.message, true); }
                finally { setBusy(false); }
              }}><Search size={15} />{p.research_provider === "browser" ? "重新检索网页资料" : "用 computer-use 补全中文详情"}</button>
              <ComputerUseStatus task={p.research_task || null} provider={p.research_provider} notice={notice} onChange={load} />
            </>}
            <ClaimList title="主要功能" claims={chineseClaims(summary.functions)} />
            <ClaimList title="特色与创新点" claims={chineseClaims(summary.innovations)} />
            <ClaimList title="适用场景" claims={chineseClaims(summary.use_cases)} />
            <ClaimList title="运行与部署要求" claims={chineseClaims(summary.requirements)} />
            <ClaimList title="搜索补充的日期信息" claims={chineseClaims(summary.date_facts)} />
            {!p.collected && (
              <button
                className="btn primary"
                onClick={() => patch({ collected: true })}
              >
                <Plus size={16} />
                加入资料库并补全
              </button>
            )}
          </section>
          <section className="panel">
            <h2>官方资料与来源</h2>
            {p.description && <details><summary>查看官方原始简介</summary><p className="muted">{p.description}</p></details>}
            <div className="source-links">
              <a
                href={safeLink(meta.readme_url || meta.html_url)}
                target="_blank"
                rel="noreferrer"
              >
                <BookOpen size={17} />
                <abbr title="仓库说明文档">README</abbr>
                <ExternalLink size={14} />
              </a>
              {meta.homepage && (
                <a
                  href={safeLink(meta.homepage)}
                  target="_blank"
                  rel="noreferrer"
                >
                  官方网站
                  <ExternalLink size={14} />
                </a>
              )}
              <a
                href={`https://github.com/${p.full_name}/releases`}
                target="_blank"
                rel="noreferrer"
              >
                版本发布
                <ExternalLink size={14} />
              </a>
            </div>
            {summary.links?.length > 0 && (
              <details>
                <summary><abbr title="仓库说明文档">README</abbr> 中的相关链接</summary>
                <div className="related-links">
                  {summary.links.map((l: any, i: number) => (
                    <a
                      key={i}
                      href={safeLink(l.url)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {l.label}
                      <ArrowUpRight size={13} />
                    </a>
                  ))}
                </div>
              </details>
            )}
            <details>
              <summary>查看 <abbr title="仓库说明文档">README</abbr> 原文</summary>
              <pre className="readme">{p.readme || "尚未获取 README"}</pre>
            </details>
            {summary.web_sources?.length > 0 && <details open>
              <summary>{["computer_use", "browser"].includes(summary.mode) ? "浏览器核对来源" : "搜索补全来源"}（{summary.web_sources.length}）</summary>
              <div className="related-links">{summary.web_sources.map((s: any) => (
                <a key={s.url} href={safeLink(s.url)} target="_blank" rel="noreferrer">{s.title || s.url}<ArrowUpRight size={13} /></a>
              ))}</div>
            </details>}
            <p className="source-meta">
              采集时间：{date(p.fetched_at)}（北京时间）
              {meta.readme_blob_sha &&
                ` / README SHA ${meta.readme_blob_sha.slice(0, 10)}`}
            </p>
            <button
              className="btn secondary small"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api(`/projects/${id}/refresh`, { method: "POST" });
                  await load();
                  notice(p.research_provider === "browser" ? "已加入后台浏览器检索队列" : p.research_provider === "computer_use" ? "已派发 computer-use 任务，可在上方复制执行指令" : "已提交刷新任务，完成后重新打开详情查看");
                } catch (e: any) {
                  notice(e.message, true);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <RefreshCw size={14} />
              刷新资料与摘要
            </button>
          </section>
          {p.images && p.images.length > 0 && (
            <section className="panel">
              <h2>
                来源截图 <span className="count">{p.images.length}</span>
              </h2>
              <div className="source-images">
                {p.images.map((i) => (
                  <a
                    key={i.id}
                    href={`/api/images/${i.id}/file`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img src={`/api/images/${i.id}/file`} alt={i.filename} />
                  </a>
                ))}
              </div>
            </section>
          )}
        </div>
        <aside>
          <section className="panel project-classification">
            <h2>用途与检索</h2>
            <p className="muted">最多选择 3 个用途。手动调整后会保留你的分类。</p>
            <div className="category-editor">{(p.category_options || []).map(c => <label key={c.id}><input type="checkbox" checked={(p.categories || []).includes(c.id)} disabled={!(p.categories || []).includes(c.id) && (p.categories || []).filter(id => id !== "uncategorized").length >= 3} onChange={e => {
              const current = (p.categories || []).filter(id => id !== "uncategorized");
              const categories = c.id === "uncategorized" ? ["uncategorized"] : e.target.checked ? [...current, c.id] : current.filter(id => id !== c.id);
              patch({ categories: categories.length ? categories : ["uncategorized"] });
            }} />{c.label}</label>)}</div>
            <label>检索关键词<input value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="用逗号分隔，如 视频剪辑, video editing" /></label>
            <button className="btn secondary small" onClick={() => patch({ keywords: keywords.split(/[,，]/).map(v => v.trim()).filter(Boolean) })}><Check size={15} />保存检索关键词</button>
          </section>
          <section className="panel timeline">
            <h2>项目时间线</h2>
            <div>
              <span />
              仓库创建<p>{date(meta.created_at)}</p>
            </div>
            <div>
              <span />
              首次正式 Release
              <p>
                {meta.first_release
                  ? date(meta.first_release.published_at)
                  : meta.releases_complete === false
                    ? "首次发布时间尚未核实"
                    : "未发现正式 Release"}
              </p>
            </div>
            <div>
              <span />
              最新正式 Release
              <p>
                {meta.latest_release ? (
                  <a
                    href={safeLink(meta.latest_release.html_url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {meta.latest_release.tag_name} ·{" "}
                    {date(meta.latest_release.published_at)}
                  </a>
                ) : (
                  "未发现正式 Release"
                )}
              </p>
            </div>
            <div>
              <span />
              最近代码推送<p>{date(meta.pushed_at)}</p>
            </div>
            <small>所有日期以北京时间展示。</small>
          </section>
          <section className="panel personal">
            <h2>我的整理</h2>
            <label>
              研究状态
              <select
                value={p.study_status}
                onChange={(e) => patch({ study_status: e.target.value })}
              >
                <option>待研究</option>
                <option>已读</option>
                <option>已使用</option>
              </select>
            </label>
            <label>
              个人标签
              <input
                placeholder="用逗号分隔，如 OCR, 开发工具"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </label>
            <label>
              项目笔记
              <textarea
                rows={5}
                placeholder="记录你的想法或使用计划…"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
            <button
              className="btn secondary"
              onClick={() =>
                patch({
                  notes,
                  tags: tags
                    .split(/[,，]/)
                    .map((t) => t.trim())
                    .filter(Boolean),
                })
              }
            >
              <Check size={15} />
              保存整理
            </button>
          </section>
          <section className="panel">
            <h2>Star 观察</h2>
            <p className="muted">
              已保存 {p.snapshots?.length || 0}{" "}
              个采样点。趋势榜将在积累足够历史后开放。
            </p>
            {p.snapshots?.slice(-5).map((s) => (
              <div className="snapshot" key={s.date}>
                <span>{s.date}</span>
                <b>{num(s.stars)}</b>
              </div>
            ))}
          </section>
        </aside>
      </div>
    </>
  );
}

function ClaimList({ title, claims }: { title: string; claims?: Claim[] }) {
  return (
    <div className="claim-section">
      <h3>{title}</h3>
      {claims?.length ? (
        <ul>
          {claims.map((c, i) => (
            <li key={i}>
              <p>{c.text}</p>
              <details>
                <summary>
                  核对来源 <ArrowUpRight size={12} />
                </summary>
                <blockquote>{c.quote}</blockquote>
                <a href={safeLink(c.source)} target="_blank" rel="noreferrer">
                  打开原始资料
                  <ExternalLink size={12} />
                </a>
              </details>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">暂无可核验的中文归纳。</p>
      )}
    </div>
  );
}

function Discover({ notice, onSelect, onChange }: any) {
  const [data, setData] = useState<any>({ items: [] }),
    [busy, setBusy] = useState(false),
    [rule, setRule] = useState<any>(null);
  const load = () =>
    api("/discoveries")
      .then(setData)
      .catch((e: any) => notice(e.message, true));
  useEffect(() => {
    load();
    api("/settings").then((r) => setRule(r.discovery_rule));
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, []);
  return (
    <>
      <div className="discovery-intro">
        <div>
          <span className="pill">
            <Compass size={14} />
            近期新项目榜
          </span>
          <h2>新的工具，新的可能。</h2>
          <p>
            按创建时间和累计 Star
            筛选。榜单展示有限候选，覆盖范围以采集结果为准。
          </p>
        </div>
        <button
          className="btn primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await api("/discoveries/refresh", { method: "POST" });
              notice("发现任务已提交，可在任务中心查看进度");
            } catch (e: any) {
              notice(e.message, true);
            } finally {
              setBusy(false);
            }
          }}
        >
          <RefreshCw size={16} className={busy ? "spin" : ""} />
          立即发现
        </button>
      </div>
      {rule && (
        <div className="filter-bar discovery-filters">
          <span>
            <Clock3 size={15} />近 {rule.days} 天创建
          </span>
          <span>
            <Star size={15} />≥ {rule.min_stars} Star
          </span>
          <span>{rule.language || "全部语言"}</span>
          <span>{rule.topic || "全部领域"}</span>
          <small>
            每日 {String(rule.hour).padStart(2, "0")}:00 北京时间 ·{" "}
            {rule.enabled ? "自动运行" : "已暂停"}
          </small>
        </div>
      )}
      <div className="list-meta">
        <span>
          {data.fetched_at
            ? `更新于 ${date(data.fetched_at)} / 匹配 ${data.total_count} 项，展示前 ${data.items.length} 项`
            : "尚未生成榜单，点击“立即发现”开始采集"}
        </span>
      </div>
      {data.incomplete && (
        <p className="info-note">GitHub 返回结果不完整，当前榜单仅供参考。</p>
      )}
      {data.items.length ? (
        <div className="discovery-list">
          {data.items.map((p: Project, i: number) => (
            <article key={p.id}>
              <span className={"rank " + (i < 3 ? "top-rank" : "")}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <button className="card-link" onClick={() => onSelect(p.id)}>
                  <h3>
                    {p.full_name}
                    <ArrowUpRight size={15} />
                  </h3>
                </button>
                <p>{p.description || "仓库未提供简介"}</p>
                <small>
                  {p.language || "未标注"} <span>·</span>{" "}
                  {date(p.metadata.created_at)} 创建
                </small>
              </div>
              <span className="discover-stars">
                <Star size={15} />
                {num(p.stars)}
              </span>
              <button
                className="btn secondary small"
                disabled={p.collected}
                onClick={async () => {
                  try {
                    await api(`/projects/${p.id}`, {
                      method: "PATCH",
                      body: JSON.stringify({ collected: true }),
                    });
                    load();
                    onChange();
                    notice("已加入资料库，正在补全详细档案");
                  } catch (e: any) {
                    notice(e.message, true);
                  }
                }}
              >
                {p.collected ? <Check size={14} /> : <Plus size={14} />}{" "}
                {p.collected ? "已收集" : "收集项目"}
              </button>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          icon={Compass}
          title="下一次发现，正在等待"
          text="系统将根据你的规则从 GitHub 获取真实项目，结果不会使用演示数据填充。"
        />
      )}
    </>
  );
}

function Settings({ notice }: { notice: Notice }) {
  const [data, setData] = useState<any>(null),
    [rule, setRule] = useState<any>(null);
  useEffect(() => {
    api("/settings")
      .then((r) => {
        setData(r);
        setRule(r.discovery_rule);
      })
      .catch((e) => notice(e.message, true));
  }, []);
  if (!data) return <Loading />;
  return (
    <div className="settings-grid">
      <section className="panel">
        <h2>服务连接</h2>
        <Service
          label="PaddleOCR 本地识别"
          ok={data.ocr.installed}
          text={
            data.ocr.installed
              ? "依赖已安装；首次识别可能下载模型"
              : "尚未安装：运行 scripts/setup.ps1 -WithOcr"
          }
        />
        <Service
          label="GitHub API"
          ok={data.github_authenticated}
          text={
            data.github_authenticated
              ? "已配置 Token"
              : "公开接口可用；配置 GITHUB_TOKEN 可提高额度"
          }
        />
        <Service
          label="中文 AI 摘要"
          ok={data.ai_configured}
          text={
            data.ai_configured
              ? `已配置 / 每日最多 ${data.ai_daily_limit} 次`
              : "在 .env 中配置 AI_BASE_URL、AI_API_KEY 和 AI_MODEL"
          }
        />
        <Service label="项目研究检索" ok={!!data.research_agent?.executor?.online}
          text={data.research_agent?.provider === "browser" ? `后台 Chrome / ${data.research_agent?.executor?.online ? "已在线" : "未运行"} / ${data.research_agent?.executor?.waiting || 0} 项等待自动领取` : data.research_agent?.provider === "computer_use"
            ? `computer-use / ${data.research_agent?.executor?.waiting || 0} 项等待桌面执行器接手`
            : "DeepSeek Search（旧检索模式）"} />
        <p className="info-note">
          <ShieldCheck size={16} />
          {data.privacy}
        </p>
        <p className="muted">
          GitHub Token 可在下方配置并立即生效。AI 服务通过项目根目录 .env 配置，修改后重启服务。
        </p>
        <GitHubTokenForm configured={data.github_authenticated}
          onConfigured={() => setData({ ...data, github_authenticated: true })} notice={notice} />
      </section>
      <PasswordForm notice={notice} />
      <form
        className="panel"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api("/discovery-rule", {
              method: "PUT",
              body: JSON.stringify(rule),
            });
            notice("自动发现规则已保存");
          } catch (e: any) {
            notice(e.message, true);
          }
        }}
      >
        <div className="panel-heading">
          <h2>自动发现规则</h2>
          <label className="switch-label">
            <input
              type="checkbox"
              checked={rule.enabled}
              onChange={(e) => setRule({ ...rule, enabled: e.target.checked })}
            />
            每日运行
          </label>
        </div>
        <div className="form-grid">
          <label>
            创建时间范围
            <select
              value={rule.days}
              onChange={(e) => setRule({ ...rule, days: +e.target.value })}
            >
              <option value={7}>最近 7 天</option>
              <option value={30}>最近 30 天</option>
              <option value={90}>最近 90 天</option>
            </select>
          </label>
          <label>
            最低 Star
            <input
              type="number"
              min={0}
              max={1000000}
              value={rule.min_stars}
              onChange={(e) => setRule({ ...rule, min_stars: +e.target.value })}
            />
          </label>
          <label>
            编程语言
            <input
              placeholder="例如 Python（留空不限）"
              value={rule.language}
              onChange={(e) => setRule({ ...rule, language: e.target.value })}
            />
          </label>
          <label>
            Topic
            <input
              placeholder="例如 machine-learning"
              value={rule.topic}
              onChange={(e) => setRule({ ...rule, topic: e.target.value })}
            />
          </label>
          <label>
            每日执行时间（北京时间）
            <select
              value={rule.hour}
              onChange={(e) => setRule({ ...rule, hour: +e.target.value })}
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </select>
          </label>
          <label>
            每次采集数量
            <input
              type="number"
              min={1}
              max={100}
              value={rule.limit}
              onChange={(e) => setRule({ ...rule, limit: +e.target.value })}
            />
          </label>
        </div>
        <button className="btn primary">
          <Check size={16} />
          保存规则
        </button>
      </form>
      <section className="panel">
        <h2>数据与运行</h2>
        <p className="muted">
          {data.storage} / {data.worker}
        </p>
        <p>
          数据保存在服务器 data
          目录。请定期备份数据库与图片，导出文件只包含项目资料。
        </p>
        <a className="btn secondary" href="/api/export" download>
          <ArrowDownToLine size={16} />
          导出项目 JSON
        </a>
      </section>
      <section className="panel">
        <h2>手机连接说明</h2>
        <p>
          同一 Wi-Fi 下，使用电脑的局域网地址生成二维码，服务需监听 0.0.0.0:8000
          并允许防火墙访问。
        </p>
        <p className="muted">
          手机使用移动网络时，需要可访问的公网 HTTPS 域名。二维码的 localhost
          地址只适用于电脑本机。
        </p>
        <p>
          配置地址：{data.public_base_url || "尚未配置，可在二维码窗口填写"}
        </p>
      </section>
    </div>
  );
}
function Service({ label, ok, text }: any) {
  return (
    <div className="service">
      <span className={"service-icon " + (ok ? "ready" : "")}>
        {ok ? <CheckCircle2 size={18} /> : <Settings2 size={18} />}
      </span>
      <div>
        <b>{label}</b>
        <p>{text}</p>
      </div>
      <span className={"pill " + (ok ? "green" : "")}>
        {ok ? "已就绪" : "待配置"}
      </span>
    </div>
  );
}

function Jobs({ notice }: { notice: Notice }) {
  const [jobs, setJobs] = useState<any[]>([]);
  const [executor, setExecutor] = useState<any>(null);
  const load = () =>
    Promise.all([api("/jobs"), api("/browser-service/status")])
      .then(([rows, state]) => { setJobs(rows); setExecutor(state); })
      .catch((e) => notice(e.message, true));
  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);
  const cooling = executor?.online && executor?.status === "cooldown";
  return <>
    {executor && ["browser", "computer_use"].includes(executor.provider) && <div className="browser-service-banner" role="status">
      {executor.online ? <CheckCircle2 size={20} /> : <Clock3 size={20} />}
      <div><b>{executor.provider === "browser" ? cooling ? "浏览器服务在线 · 网页限流冷却中" : executor.online ? "后台浏览器服务已在线" : "后台浏览器服务未运行" : "当前使用会话式 computer-use"}</b>
          <p>{executor.provider === "browser" ? `${executor.waiting} 项等待自动领取${!cooling && executor.online && executor.current_job ? "，正在处理任务" : ""}。${executor.error || (executor.online ? "服务会持续处理队列，网页检索完成后自动校验入库。" : "任务已保留，请启动后台浏览器服务后继续。")}` : "需要授权桌面会话领取任务；安装插件不会自动启动后台执行器。"}</p>
          {cooling && executor.cooldown_until && <p>预计恢复：{new Date(executor.cooldown_until).toLocaleString("zh-CN")}。期间整个队列暂停网页请求，任务和已读取资料已保留。</p>}</div>
    </div>}
    {jobs.length ? (
    <div className="jobs-list">
      {jobs.map((j) => (
        <div className="job-row" key={j.id}>
          <span className={"job-icon " + j.status}>
            {j.status === "completed" ? (
              <CheckCircle2 size={21} />
            ) : j.status === "failed" ? (
              <XCircle size={21} />
            ) : ["waiting_browser", "queued", "cancelled"].includes(j.status) ? (
              <Clock3 size={21} />
            ) : (
              <LoaderCircle className="spin" size={21} />
            )}
          </span>
          <div>
            <h3>
              {{
                recognize: "截图识别",
                research: "项目研究智能体",
                auto_confirm: "自动确认与补全智能体",
                computer_use: "浏览器项目检索",
                curate_project: "中文资料与分类智能体",
                curate_library: "资料库整理智能体",
                collect: "项目资料补全",
                discovery: "GitHub 自动发现",
              }[j.kind as string] || j.kind}
            </h3>
            <p>{j.error || j.stage}</p>
            <small>
              {date(j.created_at)} / {j.browser_attempts != null ? `浏览器已尝试 ${j.browser_attempts} 次` : `已尝试 ${j.attempts} 次`}
              {["queued", "waiting_browser"].includes(j.status) &&
                j.error &&
                ` / 下次重试不早于 ${new Date(Math.max(Date.parse(j.available_at), Date.parse(executor?.cooldown_until || "") || 0)).toLocaleString("zh-CN")}`}
            </small>
          </div>
          <span className={"status status-" + j.status}>
            {statusText[j.status]}
          </span>
          {j.status === "failed" && (
            <button
              className="btn secondary small"
              onClick={async () => {
                try {
                  await api(`/jobs/${j.id}/retry`, { method: "POST" });
                  load();
                } catch (e: any) {
                  notice(e.message, true);
                }
              }}
            >
              <RefreshCw size={14} />
              重试
            </button>
          )}
        </div>
      ))}
    </div>
  ) : (
    <Empty
      icon={CheckCircle2}
      title="一切就绪"
      text="上传截图或运行自动发现后，可以在这里跟踪任务进度。"
    />
  )}</>;
}

function PhoneModal({
  onClose,
  notice,
}: {
  onClose: () => void;
  notice: Notice;
}) {
  const [base, setBase] = useState(""),
    [suggestions, setSuggestions] = useState<string[]>([]),
    [session, setSession] = useState<any>(null),
    [busy, setBusy] = useState(false);
  const baseEdited = useRef(false);
  useEffect(() => {
    api("/network")
      .then((r) => {
        if (!baseEdited.current) setBase(r.configured || r.suggestions[0] || location.origin);
        setSuggestions(r.suggestions);
      })
      .catch((e) => notice(e.message, true));
  }, []);
  const revoke = async () => {
    if (session)
      await api(`/upload-sessions/${session.id}`, { method: "DELETE" });
    setSession(null);
  };
  return (
    <Modal title="用手机，随手收集" onClose={onClose}>
      <p className="muted">
        手机扫码打开上传网页，无需安装 App。请确认手机能够访问下面的服务地址。
      </p>
      <label>
        手机可访问的系统地址
        <input
          list="network-addresses"
          value={base}
          placeholder="http://192.168.1.100:8000"
          onInput={() => { baseEdited.current = true; }}
          onChange={(e) => setBase(e.target.value)}
        />
        <datalist id="network-addresses">
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </label>
      {!session ? (
        <button
          className="btn primary full"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setSession(
                await api("/upload-sessions", {
                  method: "POST",
                  body: JSON.stringify({ base_url: base }),
                }),
              );
            } catch (e: any) {
              notice(e.message, true);
            } finally {
              setBusy(false);
            }
          }}
        >
          <QrCode size={17} />
          生成临时二维码
        </button>
      ) : (
        <div className="qr-result">
          <img src={session.qr} alt="手机上传二维码" />
          <b>使用手机相机扫描二维码</b>
          <p>10 分钟内有效 / 仅授予本次上传权限</p>
          {session.loopback && (
            <p className="error-text">
              该地址只支持本机，请改用局域网 IP 或公网域名。
            </p>
          )}
          <a href={safeLink(session.url)} target="_blank" rel="noreferrer">
            在浏览器测试上传页 <ExternalLink size={13} />
          </a>
          <button
            className="text-btn muted"
            onClick={async () => {
              try {
                await revoke();
                notice("本次二维码权限已撤销");
              } catch (e: any) {
                notice(e.message, true);
              }
            }}
          >
            撤销二维码及上传会话
          </button>
        </div>
      )}
      <div className="info-note">
        <ShieldCheck size={16} />
        手机只允许上传与查看本次进度，无法访问已有项目。关闭窗口不会撤销权限。
      </div>
    </Modal>
  );
}
function LinkModal({ onClose, notice, onChange }: any) {
  const [name, setName] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal title="添加一个好项目" onClose={onClose}>
      <p className="muted">
        粘贴 GitHub 仓库地址，我们会自动获取资料并整理档案。
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("/projects/import", {
              method: "POST",
              body: JSON.stringify({ full_name: name }),
            });
            notice("项目补全任务已提交，可在任务中心查看");
            onChange();
            onClose();
          } catch (e: any) {
            notice(e.message, true);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          GitHub 仓库
          <input
            autoFocus
            required
            value={name}
            placeholder="https://github.com/PaddlePaddle/PaddleOCR"
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button className="btn primary full" disabled={busy}>
          {busy ? (
            <LoaderCircle className="spin" size={17} />
          ) : (
            <Plus size={17} />
          )}
          添加到资料库
        </button>
      </form>
    </Modal>
  );
}

function Mobile() {
  const [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [batch, setBatch] = useState<any>(null);
  useEffect(() => {
    const token = new URLSearchParams(location.hash.slice(1)).get("token");
    if (token) {
      history.replaceState(null, "", "/mobile");
      sessionStorage.removeItem("uploadCredential");
      sessionStorage.removeItem("lastUploadBatch");
      setBatch(null);
      api("/upload-sessions/exchange", {
        method: "POST",
        body: JSON.stringify({ token }),
      })
        .then((r) => {
          sessionStorage.setItem("uploadCredential", r.credential);
          setReady(true);
        })
        .catch((e) => setError(e.message));
    } else setReady(!!sessionStorage.getItem("uploadCredential"));
    const old = sessionStorage.getItem("lastUploadBatch");
    if (old) setBatch({ id: old, images: [] });
  }, []);
  useEffect(() => {
    const handle = () => {
      const id = sessionStorage.getItem("lastUploadBatch");
      if (id) setBatch({ id, images: [] });
    };
    window.addEventListener("upload-batch-created", handle);
    return () => window.removeEventListener("upload-batch-created", handle);
  }, []);
  useEffect(() => {
    if (!batch?.id) return;
    const load = () =>
      api(`/import-batches/${batch.id}`)
        .then(setBatch)
        .catch((e) => setError(e.message));
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [batch?.id]);
  return (
    <div className="mobile-page">
      <div className="brand">
        <span className="brand-icon">
          <Github />
        </span>
        <span>
          GitHub Lens<small>手机上传</small>
        </span>
      </div>
      <h1>
        好项目，
        <br />
        现在就收好。
      </h1>
      <p>
        选择相册里的截图，
        <br />
        电脑端会自动接收并整理项目。
      </p>
      {error && <div className="info-note error-text">{error}</div>}
      {ready ? (
        <>
          <UploadBox
            notice={(text, err) => (err ? setError(text) : setMessage(text))}
            onDone={async () => {
              setMessage("图片已接收，电脑端正在识别。");
            }}
          />
          {message && (
            <p className="success-message">
              <CheckCircle2 size={18} />
              {message}
            </p>
          )}
          {batch?.images?.length > 0 && (
            <section className="panel mobile-receipt">
              <h2>本次上传回执</h2>
              {batch.images.map((i: ImageItem) => (
                <div key={i.id}>
                  <span>{i.filename}</span>
                  <span className={"status status-" + i.status}>
                    {statusText[i.status]}
                  </span>
                </div>
              ))}
            </section>
          )}
          <p className="info-note">
            <ShieldCheck size={16} />
            <span><abbr title="文字识别">OCR</abbr> 在服务器本地完成；待处理图片的智能研究会发送截图至配置的 <abbr title="人工智能">AI</abbr>
            服务并联网搜索。上传凭证仅限本次会话。</span>
          </p>
        </>
      ) : (
        <Empty
          icon={QrCode}
          title={error ? "请重新扫码连接" : "等待连接"}
          text="请从电脑端“手机上传”生成新的二维码。"
        />
      )}
    </div>
  );
}
function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={"modal " + (wide ? "wide" : "")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-heading">
          <h2>{title}</h2>
          <button className="icon-btn" aria-label="关闭窗口" onClick={onClose}>
            <X size={21} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
function Empty({ icon: Icon, title, text }: any) {
  return (
    <div className="empty">
      <span>
        <Icon size={27} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function Loading() {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={23} />
      <span>正在加载…</span>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
