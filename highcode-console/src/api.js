async function readError(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string" && body.detail) {
      return body.detail;
    }
  } catch {
    // 非 JSON 响应时使用状态码
  }
  return `请求失败 (${response.status})`;
}

export async function deployWhl({ userId, spaceId, file, name, version, port }) {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  if (version) {
    form.append("version", version);
  }
  if (port) {
    form.append("port", port);
  }
  const response = await fetch("/api/v1/agents/deploy-whl", {
    method: "POST",
    headers: {
      "X-User-ID": userId,
      "X-Space-ID": spaceId,
    },
    body: form,
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function listAgents(headers) {
  const response = await fetch("/api/v1/agents", { headers });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const body = await response.json();
  return body.deployments || [];
}

export async function queryAgent(deploymentId, payload) {
  const response = await fetch(`/api/v1/agents/${deploymentId}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    throw new Error(await readError(response));
  }
  return response;
}

export async function deleteAgent(deploymentId, userId) {
  const response = await fetch(`/api/v1/agents/${deploymentId}`, {
    method: "DELETE",
    headers: {
      "X-User-ID": userId,
    },
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}
