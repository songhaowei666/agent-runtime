# 按部署 ID 转发对话

## 背景

Runtime 管理服务（默认 `8186`）只负责部署、查询、删除。对话接口在 Agent 进程上：

- `GET /health`
- `POST /query`（SSE）
- `POST /reset_conversation`

部署成功后，调用方拿到 `deployment_id` 和 `url`，之后必须直连 `url`。管理服务没有按部署 ID 转发的路由。

外部调用方往往只保存 `deployment_id`，不适合再维护每个 Agent 的地址和端口。本功能让调用方只访问 Runtime，由 Runtime 按部署记录转发到对应 Agent。

## 目标

在 `server/openjiuwen_runtime/server/main.py` 增加转发接口：

- `POST /api/v1/agents/{deployment_id}/query`
- `POST /api/v1/agents/{deployment_id}/reset_conversation`

请求体原样转发。`/query` 的 SSE 逐块返回，不等待 Agent 整段响应结束。

不修改 `service`、Agent 实现和现有部署、查询、删除接口。

## 现状

`GET /api/v1/agents/{deployment_id}` 通过 `manager.get_deployment(deployment_id)` 读取部署记录，记录中有：

- `deployment_status`
- `url`：部署时写入的 Agent 根地址，形如 `http://<IP>:<port>`
- `data.port`

`get_deployment` 只按 `deployment_id` 查库，不按 `user_id` / `space_id` 过滤。租户中间件当前是 `require_tenant=False`。转发接口与现有查询接口保持一致，不新增租户校验。

Agent 的 `/query` 在 `service/openjiuwen_runtime/service/app/agent_app.py` 中返回 `StreamingResponse`，媒体类型 `text/event-stream`，每块为 `data: {json}\n\n`。`/reset_conversation` 返回 JSON：`{"status": "ok", "message": "..."}`。

探活时若配置的 `IP` 从本机不可达，`DeploymentManager._health_url_with_loopback_host` 会把主机换成 `127.0.0.1` 再试。转发必须使用同一套地址选择，否则本机部署会出现管理服务探活成功、转发失败。

## 接口

### 转发查询

`POST /api/v1/agents/{deployment_id}/query`

请求体与 Agent 的 `QueryRequest` 一致，Runtime 不改字段、不补默认值：

| 字段 | 说明 |
| --- | --- |
| `messages` | 当前消息列表 |
| `conversation_id` | 对话 ID |
| `user_id` | 用户 ID |
| `space_id` | 工作空间 ID |
| `stream` | 是否流式 |

成功时：

- 状态码与上游 Agent 一致
- `Content-Type: text/event-stream`
- 响应头包含 `Cache-Control: no-cache, no-transform`、`Connection: keep-alive`、`X-Accel-Buffering: no`
- 响应体按上游字节流原样输出

### 转发重置

`POST /api/v1/agents/{deployment_id}/reset_conversation`

请求体原样转发，至少包含 `conversation_id`。成功时把上游 JSON 和状态码原样返回。

## 处理流程

1. `manager.get_deployment(deployment_id)`。
2. 记录不存在：`404`，`detail` 为 `Deployment {deployment_id} not found`。
3. `deployment_status` 不是 `running`，或 `url` 为空：`409`，说明部署未就绪。
4. 目标地址先用记录中的 `url`。连接失败时，若主机不是回环地址，改用 `127.0.0.1` 加原端口再请求一次。两次都失败：`502`。
5. 把调用方的请求体、`Content-Type` 转发到 `{目标地址}/query` 或 `{目标地址}/reset_conversation`。
6. `/query` 使用流式响应，客户端断开时关闭上游连接。
7. 上游返回 4xx/5xx 时，把状态码和响应体传回调用方，不包装成 Runtime 的 500。

## 错误

| 条件 | 状态码 |
| --- | --- |
| 部署不存在 | 404 |
| 非 running，或没有 url | 409 |
| 两个地址都连不上 | 502 |
| Agent 返回的 HTTP 错误 | 原样透传 |

## 不做

- 不转发 `/health`、`/agent_detail`，也不提供任意路径代理。
- 不改部署流程，不在部署接口里增加转发地址。
- 不解析、不改写 SSE 事件。
- 不在本功能中启用租户强制校验。
