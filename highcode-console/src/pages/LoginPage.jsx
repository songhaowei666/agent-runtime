import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CODE_PATTERN, saveSession } from "../session";

export default function LoginPage() {
  const navigate = useNavigate();
  const [userId, setUserId] = useState("");
  const [spaceId, setSpaceId] = useState("");
  const [error, setError] = useState("");

  function submit(event) {
    event.preventDefault();
    const userCode = userId.trim();
    const spaceCode = spaceId.trim();
    if (!CODE_PATTERN.test(userCode) || !CODE_PATTERN.test(spaceCode)) {
      setError("用户编码和用户组编码只能包含字母、数字、下划线和短横线");
      return;
    }
    saveSession(userCode, spaceCode);
    navigate("/console", { replace: true });
  }

  return (
    <main className="login-page">
      <form className="card login-card" onSubmit={submit}>
        <h1>高码智能体</h1>
        <p className="muted">填写用户编码和用户组编码后进入控制台。</p>
        <label>
          用户编码
          <input
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          用户组编码
          <input
            value={spaceId}
            onChange={(event) => setSpaceId(event.target.value)}
            autoComplete="organization"
            required
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit">进入控制台</button>
      </form>
    </main>
  );
}
