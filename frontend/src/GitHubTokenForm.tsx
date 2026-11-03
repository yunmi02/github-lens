import { useState } from "react";
import { ExternalLink, LoaderCircle, ShieldCheck } from "lucide-react";
import { api } from "./api";

export default function GitHubTokenForm({ configured, onConfigured, notice }: {
  configured: boolean; onConfigured: () => void; notice: (message: string, error?: boolean) => void;
}) {
  const [token, setToken] = useState(""), [busy, setBusy] = useState(false), [rates, setRates] = useState<any>(null);
  return <form className="github-token-form" onSubmit={async e => {
    e.preventDefault(); setBusy(true);
    try {
      const result = await api("/settings/github-token", { method: "POST", body: JSON.stringify({ token }) });
      setToken(""); setRates(result.rate_limit); onConfigured(); notice(result.message);
    } catch (e: any) { notice(e.message, true); }
    finally { setBusy(false); }
  }}>
    <h3>配置 GitHub Token</h3>
    <p className="muted">在 GitHub 生成 Fine-grained Token，保留公开仓库只读访问即可。下方链接已预填名称及 90 天有效期。</p>
    <a className="text-btn" href="https://github.com/settings/personal-access-tokens/new?name=GitHub%20Lens&description=Read%20public%20repositories%20for%20GitHub%20Lens&expires_in=90" target="_blank" rel="noreferrer">
      前往 GitHub 创建令牌 <ExternalLink size={13} />
    </a>
    <label>GitHub Token
      <input type="password" required autoComplete="off" spellCheck={false} maxLength={512}
        placeholder={configured ? "已配置；粘贴新令牌可替换" : "粘贴 GitHub 生成的 Token"}
        value={token} onChange={e => setToken(e.target.value)} />
    </label>
    <button className="btn primary small" disabled={busy || !token.trim()}>
      {busy ? <LoaderCircle size={15} className="spin" /> : <ShieldCheck size={15} />}
      {busy ? "正在验证 GitHub" : "验证并保存 Token"}
    </button>
    {rates && <p className="success-message">验证时可用额度：普通接口 {rates.core.remaining}/{rates.core.limit}，搜索接口 {rates.search.remaining}/{rates.search.limit}。已立即生效。</p>}
    <p className="muted">令牌仅保存于服务器配置，不会回显。验证失败会保留原配置。</p>
  </form>;
}
