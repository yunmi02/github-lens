import { useState } from "react";
import { KeyRound } from "lucide-react";
import { api } from "./api";

export default function PasswordForm({ notice }: { notice: (message: string, error?: boolean) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  return <form className="panel" onSubmit={async e => {
    e.preventDefault();
    if (next !== confirm) { notice("两次输入的新密码不一致", true); return; }
    setBusy(true);
    try {
      await api("/auth/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) });
      setCurrent(""); setNext(""); setConfirm("");
      notice("密码已修改，其他设备的旧登录已失效");
    } catch (error: any) { notice(error.message, true); }
    finally { setBusy(false); }
  }}>
    <h2>账号安全</h2>
    <p className="muted">修改密码后，其他设备需要重新登录，当前会话继续可用。</p>
    <label>当前密码<input type="password" required maxLength={200} autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} /></label>
    <label>新密码<input type="password" required minLength={10} maxLength={200} autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} /></label>
    <label>确认新密码<input type="password" required minLength={10} maxLength={200} autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} /></label>
    <button className="btn secondary" disabled={busy}><KeyRound size={15} />{busy ? "正在修改…" : "修改密码"}</button>
  </form>;
}
