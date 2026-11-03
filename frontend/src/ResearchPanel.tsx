import { useEffect, useRef, useState } from "react";
import {
  Sparkles,
  LoaderCircle,
  Search,
  ExternalLink,
  ArrowUpRight,
  CheckCircle2,
} from "lucide-react";
import { api, date, ImageItem, safeLink } from "./api";
import ComputerUseStatus, { browserTaskActive } from "./ComputerUseStatus";

type Props = {
  image: ImageItem;
  onImage: (image: ImageItem) => void;
  onSelect: (id: number) => void;
  notice: (text: string, error?: boolean) => void;
};

export default function ResearchPanel({
  image,
  onImage,
  onSelect,
  notice,
}: Props) {
  const [research, setResearch] = useState<any>(null),
    [busy, setBusy] = useState(false), [execution, setExecution] = useState<any>(null), [provider, setProvider] = useState("computer_use");
  const update = useRef(onImage);
  update.current = onImage;
  const load = async () => {
    const data = await api(`/recognitions/${image.id}/research`);
    setResearch(data.research);
    setExecution(data.execution);
    setProvider(data.provider || "computer_use");
    update.current(data.image);
  };
  useEffect(() => {
    load().catch((e) => notice(e.message, true));
    const timer = setInterval(() => load().catch(() => {}), 3000);
    return () => clearInterval(timer);
  }, [image.id]);
  const active = research && browserTaskActive(research.status);
  const report = research?.report || {};
  const plan = report.plan;
  return (
    <>
    <section className="research-panel auto-confirm-panel">
      <div className="research-heading">
        <h3><CheckCircle2 size={17} />自动确认与补全智能体</h3>
        <span className="pill">全部项目 / 自动关联</span>
      </div>
      <p className="muted">
        自动确认图片中识别出的全部有效项目，使用浏览器检索，保存功能、创新点、日期和来源链接。
      </p>
      <button className="btn primary" disabled={busy || active || image.status === "collecting"}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/recognitions/${image.id}/auto-confirm`, { method: "POST" });
            notice("已安排自动确认全部项目并搜索补全详情");
            await load();
          } catch (e: any) { notice(e.message, true); }
          finally { setBusy(false); }
        }}>
        {active && report.mode === "auto_confirm" ? <LoaderCircle size={16} className="spin" /> : <CheckCircle2 size={16} />}
        {active && report.mode === "auto_confirm" ? "自动确认与补全中" : "自动确认全部项目并补全"}
      </button>
      {report.mode === "auto_confirm" && (
        <p className="muted auto-confirm-result">
          {report.conclusion || `已处理 ${report.processed_count || 0} / ${report.candidate_count ?? "待识别"} 个候选，逐个保存处理进度。`}
        </p>
      )}
      {report.rejected && Object.entries(report.rejected).map(([name, reason]) => (
        <p className="muted" key={name}>已过滤 {name}：{String(reason)}</p>
      ))}
    </section>
    <section className="research-panel">
      <div className="research-heading">
        <h3>
          <Sparkles size={17} />
          项目研究智能体
        </h3>
        <span className="pill">{provider === "browser" ? "后台 Chrome / 自动检索" : provider === "computer_use" ? "computer-use / 浏览器检索" : "DeepSeek 图片理解 + 联网搜索"}</span>
      </div>
      <p className="muted">
        {provider === "browser" ? "后台 Chrome 会自动检索并核对仓库，模型理解图片线索并归纳网页资料，校验原文引用后保存详情。" : provider === "computer_use" ? "应用整理截图与 OCR 线索，由 Codex 中的 computer-use 搜索并核对仓库，结果回传后自动校验并保存。没有执行器接手时会显示等待状态。" : "智能体会将截图和线索发送至配置的 AI 服务，搜索相关仓库并整理详情。"}
      </p>
      <button
        className="btn primary"
        disabled={busy || active || image.status === "collecting"}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/recognitions/${image.id}/research`, { method: "POST" });
            notice("已交给项目研究智能体");
            await load();
          } catch (e: any) {
            notice(e.message, true);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy || active ? (
          <LoaderCircle size={16} className="spin" />
        ) : (
          <Search size={16} />
        )}
        {active
          ? "智能体研究中"
          : research
            ? "重新研究这张图片"
            : "让智能体搜索项目详情"}
      </button>
      {research && (
        <div className={"research-progress " + research.status} role="status">
          {active ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <CheckCircle2 size={15} />
          )}
          <span>{research.stage}</span>
        </div>
      )}
      {["computer_use", "browser"].includes(provider) && research && <ComputerUseStatus provider={provider} task={{ ...research, prompt: execution?.prompt }} notice={notice} onChange={() => load().catch((e) => notice(e.message, true))} />}
      {research?.error && <p className="error-text">{research.error}</p>}
      {plan && (
        <div className="research-findings">
          <h4>图片中的有用信息</h4>
          <ul>
            {plan.useful_info?.map((s: string, i: number) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
          {report.queries?.length > 0 && (
            <p>
              <b>搜索词：</b>
              {report.queries.join(" / ")}
            </p>
          )}
        </div>
      )}
      {report.projects?.length > 0 && (
        <div className="research-projects">
          <h4>已核实的项目详情</h4>
          {report.projects.map((p: any) => (
            <article key={p.repo_id}>
              <b>{p.full_name}</b>
              {p.confirmed && <span className="pill">已自动关联</span>}
              <p>{p.summary?.overview?.text || p.description}</p>
              <small>
                {p.language || "未标注语言"} / {p.stars.toLocaleString()} Star ·{" "}
                {date(p.metadata?.created_at)} 创建
              </small>
              {p.summary?.functions?.slice(0, 3).map((f: any, i: number) => (
                <p className="research-function" key={i}>
                  • {f.text}
                </p>
              ))}
              <div>
                <button
                  className="text-btn"
                  onClick={() => onSelect(p.repo_id)}
                >
                  查看完整详情
                  <ArrowUpRight size={13} />
                </button>
                <a
                  href={safeLink(p.metadata?.html_url)}
                  target="_blank"
                  rel="noreferrer"
                >
                  GitHub
                  <ExternalLink size={12} />
                </a>
              </div>
            </article>
          ))}
        </div>
      )}
      {report.sources?.length > 0 && (
        <details>
          <summary>搜索来源（{report.sources.length}）</summary>
          <div className="research-sources">
            {report.sources.map((s: any) => (
              <a
                key={s.url}
                href={safeLink(s.url)}
                target="_blank"
                rel="noreferrer"
              >
                {s.title || s.url}
                <ExternalLink size={12} />
              </a>
            ))}
          </div>
        </details>
      )}
      {report.warnings?.map((w: string, i: number) => (
        <p className="error-text" key={i}>
          {w}
        </p>
      ))}
      {report.conclusion && (
        <p className="research-conclusion">
          {report.mode === "auto_confirm" ? report.conclusion : image.status === "completed"
            ? "截图已关联项目，可在“我的项目”中查看；其他候选可按需补充关联。"
            : report.conclusion}
        </p>
      )}
    </section>
    </>
  );
}
