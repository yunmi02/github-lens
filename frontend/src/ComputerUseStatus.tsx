import { useState } from "react";
import { Copy, Clock3, LoaderCircle } from "lucide-react";
import { api } from "./api";

export const browserTaskActive = (status?: string) => ["queued", "running", "waiting_browser", "browser_running"].includes(status || "");

export default function ComputerUseStatus({ task, notice, onChange, provider = 'computer_use' }: {
  task: { job_id: string; status: string; stage: string; error?: string; prompt?: string } | null;
  notice: (message: string, error?: boolean) => void; onChange: () => void;
  provider?: string;
}) {
  const [busy, setBusy] = useState(false);
  if (!task) return null;
  const waiting = task.status === "waiting_browser", running = ["running", "browser_running"].includes(task.status);
  return <div className="computer-use-status">
    <p role="status">{running ? <LoaderCircle size={15} className="spin" /> : <Clock3 size={15} />}{task.stage}</p>
    {waiting && <p className="muted">{provider === 'browser' ? '后台浏览器服务会自动领取，完成网页检索后校验并保存资料。运行状态可在任务中心查看。' : '需要已授权的 Codex computer-use 会话接手。复制执行指令发到当前 Codex 对话，智能体会操作浏览器检索并回传来源。'}</p>}
    {task.error && <p className="error-text">{task.error}</p>}
    {browserTaskActive(task.status) && task.prompt && <button className="btn secondary small" onClick={async () => {
      try { await navigator.clipboard.writeText(task.prompt!); notice("执行指令已复制，请发到当前 Codex 对话"); }
      catch { notice("复制未成功，请从下方展开的执行指令中复制", true); }
    }}><Copy size={14} />复制 computer-use 执行指令</button>}
    {task.prompt && <details><summary>查看执行指令</summary><pre className="ocr-text">{task.prompt}</pre></details>}
    {["waiting_browser", "browser_running"].includes(task.status) && <button className="text-btn muted" disabled={busy} onClick={async () => {
      setBusy(true);
      try { await api(`/computer-use/jobs/${task.job_id}/cancel`, { method: "POST" }); onChange(); notice("任务已取消"); }
      catch (e: any) { notice(e.message, true); }
      finally { setBusy(false); }
    }}>取消本次等待</button>}
  </div>;
}
