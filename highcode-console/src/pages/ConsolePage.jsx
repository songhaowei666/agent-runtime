import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteAgent, deployWhl, listAgents } from "../api";
import { clearSession, hasSession, readSession } from "../session";

const MODULE_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$/;

function AgentTable({ title, rows, mineIds, onDelete, deletingId }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {rows.length === 0 ? (
        <p className="muted">暂无部署</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>部署 ID</th>
                <th>状态</th>
                <th>地址</th>
                <th>端口</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const canDelete = mineIds.has(row.deployment_id);
                return (
                  <tr key={row.deployment_id}>
                    <td>{row.name}</td>
                    <td className="mono">{row.deployment_id}</td>
                    <td>{row.status}</td>
                    <td className="mono">
                      {row.url ? (
                        <a href={row.url} target="_blank" rel="noreferrer">
                          {row.url}
                        </a>
                      ) : (
                        ""
                      )}
                    </td>
                    <td>{row.port ?? ""}</td>
                    <td>
                      {canDelete ? (
                        <button
                          type="button"
                          className="danger"
                          disabled={deletingId === row.deployment_id}
                          onClick={() => onDelete(row.deployment_id)}
                        >
                          删除
                        </button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function ConsolePage() {
  const navigate = useNavigate();
  const session = readSession();
  const [file, setFile] = useState(null);
  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [port, setPort] = useState("");
  const [mine, setMine] = useState([]);
  const [group, setGroup] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState("");

  const loadLists = useCallback(async () => {
    const current = readSession();
    const [mineRows, groupRows] = await Promise.all([
      listAgents({ "X-User-ID": current.userId }),
      listAgents({ "X-Space-ID": current.spaceId }),
    ]);
    setMine(mineRows);
    setGroup(groupRows);
  }, []);

  useEffect(() => {
    if (!hasSession()) {
      navigate("/login", { replace: true });
      return;
    }
    loadLists().catch((err) => setError(err.message));
  }, [loadLists, navigate]);

  function logout() {
    clearSession();
    navigate("/login", { replace: true });
  }

  async function submitUpload(event) {
    event.preventDefault();
    setError("");
    setResult(null);
    const moduleName = name.trim();
    if (!file || !file.name.endsWith(".whl")) {
      setError("请选择 .whl 文件");
      return;
    }
    if (!MODULE_PATTERN.test(moduleName)) {
      setError("模块路径需要是点分形式，例如 openjiuwen_runtime.day4_echo");
      return;
    }
    setUploading(true);
    try {
      const current = readSession();
      const deployed = await deployWhl({
        userId: current.userId,
        spaceId: current.spaceId,
        file,
        name: moduleName,
        version: version.trim(),
        port: port.trim(),
      });
      setResult(deployed);
      setFile(null);
      event.target.reset();
      await loadLists();
    } catch (err) {
      const message = err.message || "";
      setError(message.includes("not found") ? "部署不存在" : message);
    } finally {
      setUploading(false);
    }
  }

  async function removeAgent(deploymentId) {
    setError("");
    setDeletingId(deploymentId);
    try {
      await deleteAgent(deploymentId, readSession().userId);
      await loadLists();
    } catch (err) {
      const message = err.message || "";
      setError(message.includes("not found") ? "部署不存在" : message);
    } finally {
      setDeletingId("");
    }
  }

  if (!hasSession()) {
    return null;
  }

  const mineIds = new Set(mine.map((row) => row.deployment_id));

  return (
    <div className="console">
      <header className="topbar">
        <div>
          <strong>高码智能体控制台</strong>
          <span className="muted">
            用户编码 {session.userId} · 用户组编码 {session.spaceId}
          </span>
        </div>
        <button type="button" onClick={logout}>
          退出
        </button>
      </header>

      <form className="card" onSubmit={submitUpload}>
        <h2>上传</h2>
        <div className="form-grid">
          <label>
            WHL 文件
            <input
              type="file"
              accept=".whl"
              required
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
          <label>
            模块路径
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="openjiuwen_runtime.day4_echo"
              required
            />
          </label>
          <label>
            版本
            <input
              value={version}
              onChange={(event) => setVersion(event.target.value)}
              placeholder="1.0.0"
            />
          </label>
          <label>
            端口
            <input
              value={port}
              onChange={(event) => setPort(event.target.value)}
              placeholder="留空则自动分配"
              inputMode="numeric"
            />
          </label>
        </div>
        {error ? <p className="error">{error}</p> : null}
        {result ? (
          <p className="success">
            已部署 {result.deployment_id}，状态 {result.status}，地址 {result.url}
            {Array.isArray(result.base_whls) && result.base_whls.length > 0
              ? `，基础包 ${result.base_whls.join("、")}`
              : ""}
          </p>
        ) : null}
        <button type="submit" disabled={uploading}>
          {uploading ? "部署中" : "上传并部署"}
        </button>
      </form>

      <AgentTable
        title="我的智能体"
        rows={mine}
        mineIds={mineIds}
        onDelete={removeAgent}
        deletingId={deletingId}
      />
      <AgentTable
        title="本组智能体"
        rows={group}
        mineIds={mineIds}
        onDelete={removeAgent}
        deletingId={deletingId}
      />
    </div>
  );
}
