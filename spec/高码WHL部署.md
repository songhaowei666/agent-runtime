# 高码 WHL 上传部署

## 背景

高码 Agent 由各项目组单独开发，不走低码 `ir.json`。开发完成后在本地打成 WHL，上传到 Runtime 管理服务，由管理服务负责部署、查询和删除。

当前 `POST /api/v1/agents/deploy` 只接收低码 IR，并固定使用 `lowcode_agent_runner` 启动，不能部署业务方自己的 WHL。

子进程部署器已经支持「无 IR、只装 WHL」：

- 为每个 `deployment_id` 创建独立虚拟环境
- `MODE=dev` 时，先安装 `DIST_DIR` 下的 `openjiuwen_*.whl`，再安装本次上传的 Agent WHL
- 启动命令为 `python -m <package_name> --host 0.0.0.0 --port <port>`
- `package_name` 来自 `DeployAgentParams.name`（`DeploymentManager.deploy_agent` 写入 `extras["package_name"]`）

只要部署参数里不传 `ir_path`，就不会被改写成低码模块 `openjiuwen_runtime.examples.lowcode_agent`。

本仓库会持续更新。`foundation`、`service` 打出来的基础 WHL 会变，已部署 Agent 的虚拟环境不会跟着变。高码部署必须把「当时装进虚拟环境的基础包」和「以后仓库更新」分开处理。

## 目标

增加高码部署接口：

- `POST /api/v1/agents/deploy-whl`

部署成功后返回 `deployment_id`、`status`、`url`、`base_whls`。对话仍由调用方按部署 ID 访问；本功能不实现转发。

前台是独立目录里的 React 应用，包含登录页和控制台。登录页填写用户编码和用户组编码，分别作为 `user_id`、`space_id`。控制台展示该用户的智能体和该组的智能体，并可以上传、删除。

人员对应请求头 `X-User-ID`，项目组对应 `X-Space-ID`。二者写入部署记录。列表沿用现有按租户过滤。详情和删除在带了对应请求头时，必须与记录中的 `user_id`、`space_id` 一致。

实现放在新文件 `server/openjiuwen_runtime/server/highcode_deploy.py`。`main.py` 只在文件末尾调用 `register_highcode(app, manager)`。这样后面对上游 Runtime 做 merge 时，冲突范围停在这一处调用。

仓库更新后，已有高码部署通过「删除再部署」换上当前 `DIST_DIR` 里的基础包。新部署使用新的 `deployment_id`。本功能不提供原地升级。

不修改低码部署接口的函数体，不修改 `foundation`、`management`、`service`、`applications`、`cli`、Agent 模板、子进程部署器、Docker 部署器、K8s 部署器和 `scripts/deploy_dev_server.sh`。

## 现状

低码部署接口把上传文件保存为 `deploys/{deployment_id}/ir.json`，再调用 `prepare_subprocess_deployment`。该函数在 `MODE=dev` 时固定读取 `dist/lowcode_agent_runner-0.1.0-py3-none-any.whl`，在 `MODE=product` 时返回空的 WHL 路径。

`LocalSubprocessDeployer` 的安装分支：

- `MODE=dev`：安装 `settings.dist_path` 下文件名匹配 `openjiuwen_*.whl` 的基础 WHL，再安装 `whl_path` 指向的 Agent WHL。`whl_path` 不存在则部署失败。`pip_install` 返回失败时，部署器不中断，通常要等进程退出才失败。
- `MODE=product`：忽略 `whl_path`，执行 `pip install lowcode-agent-runner`。

因此本接口只在 `DEPLOY_TYPE=subprocess` 且 `MODE=dev` 时可用。`server/.env` 当前就是这两项。

虚拟环境落在 `deploys/{deployment_id}/.venv`。`create_venv` 发现目录已存在就直接返回，不会重装包。`stop` 会删掉这个 `.venv`，同目录下的业务 WHL 文件会留下。`foundation` 与 `service` 的版本号目前都是 `0.1.0`，源码更新后 wheel 文件名里的版本号通常不变。

`scripts/deploy_dev_server.sh` 每次启动会清空 `DIST_DIR` 再按当前源码构建：

| 来源 | 产物文件名 | 高码虚拟环境会不会装 |
| --- | --- | --- |
| `foundation/` | `openjiuwen_runtime_foundation-*.whl` | 会，匹配 `openjiuwen_*.whl` |
| `service/` | `openjiuwen_runtime_service-*.whl` | 会 |
| `agent-studio/backend`（目录存在时） | 以 `openjiuwen_` 开头的 studio wheel | 会 |
| `applications/lowcode_agent/` | `lowcode_agent_runner-*.whl` | 不会 |
| 上一级 `agent-core/`（目录存在时） | `openjiuwen-*.whl`（连字符） | 不会 |

管理服务自身用可编辑方式安装 `management` 和 `foundation`，重启后管理进程用的是当前源码。高码 Agent 用的是部署当时装进各自 `.venv` 的 WHL。

`GET /api/v1/agents` 已按请求中的 `user_id`、`space_id` 过滤。`GET` 和 `DELETE /api/v1/agents/{deployment_id}` 只按 `deployment_id` 查，不比对租户。租户中间件仍是 `require_tenant=False`。

Docker、K8s 部署路径要求低码 IR，本功能不使用。

## 接口

### 部署高码 Agent

`POST /api/v1/agents/deploy-whl`

`multipart/form-data`：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | Agent 的 `.whl` |
| `name` | 是 | 模块路径，作为 `python -m` 的参数，例如 `openjiuwen_runtime.day4_echo` |
| `version` | 否 | 业务包版本，写入部署记录，缺省 `1.0.0`。它不表示 Runtime 基础包版本 |
| `port` | 否 | 服务端口，缺省自动分配 |

请求头与现有部署接口相同，可选：

| 请求头 | 写入字段 |
| --- | --- |
| `X-User-ID` | `user_id` |
| `X-Space-ID` | `space_id` |

成功时状态码 `201`。响应字段与低码部署相同，并多返回 `base_whls`：

| 字段 | 说明 |
| --- | --- |
| `deployment_id` | 本次部署 ID |
| `type` | `agent` |
| `name` | 请求中的模块路径 |
| `status` | 部署状态 |
| `url` | Agent 根地址，形如 `http://<IP>:<port>` |
| `base_whls` | 本次装进虚拟环境的基础包文件名。同时写入部署记录的 `data.base_whls` |

### 详情和删除的租户比对

`GET /api/v1/agents/{deployment_id}` 与 `DELETE /api/v1/agents/{deployment_id}` 的函数体保持上游原样。比对放在 `highcode_deploy.py` 的中间件里，`register_highcode` 负责挂上。

中间件挂在 `TenantContextMiddleware` 外侧，先于它执行，因此直接读请求头 `X-User-ID`、`X-Space-ID`，不读 `request.state`。

只处理路径恰好是 `/api/v1/agents/{deployment_id}` 的 `GET` 和 `DELETE`。`/api/v1/agents`、`/api/v1/agents/deploy`、`/api/v1/agents/deploy-whl` 不进入这套比对。

- 记录不存在：保持现有 `404`。
- 请求带了 `X-User-ID`，且与记录的 `user_id` 不一致：`404`，`detail` 仍为 `Deployment {deployment_id} not found`。
- 请求带了 `X-Space-ID`，且与记录的 `space_id` 不一致：同样 `404`。
- 某个请求头没带：不比对这一项。两个头都没带时，行为与现在相同。

现有详情响应不增加字段。`base_whls` 以部署成功时的响应为准。列表接口已经按租户过滤，不改。

## 前台

前台放在仓库根目录的新目录 `highcode-console/`，使用 React 和 Vite。不放进 `server/`、`applications/` 等上游目录。`register_highcode` 把构建结果 `highcode-console/dist` 挂到 `/highcode`，并为前端路由回退到 `index.html`。开发时 Vite 把 `/api` 代理到管理服务 `http://127.0.0.1:8186`。

两个页面：

| 路径 | 作用 |
| --- | --- |
| `/highcode/login` | 登录页 |
| `/highcode/console` | 控制台 |

### 登录页

登录页收集两个编码，不接外部账号，也不要密码。两项都填写后才能进入控制台。

| 页面字段 | 请求头 | 部署记录 |
| --- | --- | --- |
| 用户编码 | `X-User-ID` | `user_id` |
| 用户组编码 | `X-Space-ID` | `space_id` |

编码只允许字母、数字、下划线和短横线。通过后写入当前标签页的 `sessionStorage`。控制台发现缺任一项时回到登录页。退出登录清除这两项并回到登录页。

### 控制台

控制台顶栏显示当前用户编码和用户组编码，并提供退出。页面主体三块：上传、我的智能体、本组智能体。

上传区字段与部署接口一致：WHL 文件、模块路径 `name`、可选的 `version` 和 `port`。提交 `POST /api/v1/agents/deploy-whl`，同时带 `X-User-ID` 和 `X-Space-ID`。成功后展示 `deployment_id`、`status`、`url`、`base_whls`，并刷新两份列表。

现有 `GET /api/v1/agents` 在两个请求头都带上时按 AND 过滤，只能得到「该用户并且该组」。控制台要分开展示，所以请求两次，每次只带一个头：

| 区块 | 请求 | 结果 |
| --- | --- | --- |
| 我的智能体 | 只带 `X-User-ID` | `user_id` 等于当前用户编码的部署 |
| 本组智能体 | 只带 `X-Space-ID` | `space_id` 等于当前用户组编码的部署 |

每行展示 `name`、`deployment_id`、`status`、`url`、`port`。

删除调用 `DELETE /api/v1/agents/{deployment_id}`，只带 `X-User-ID`。因此只能删掉该用户编码下的部署。本组列表里，`deployment_id` 也出现在「我的智能体」中的行显示删除；其余行只展示。删除成功后刷新两份列表。接口返回 `404` 时，页面显示「部署不存在」。

## 处理流程

1. 若 `settings.DEPLOY_TYPE` 不是 `subprocess`，或 `settings.MODE` 不是 `dev`：`400`，说明高码 WHL 部署只支持子进程开发模式。
2. `file` 文件名不是 `.whl`，或内容为空：`400`。
3. `name` 为空，或不是点分模块路径：`400`。模块路径只允许字母、数字、下划线，例如 `openjiuwen_runtime.day4_echo`。
4. `DIST_DIR` 下缺少 `openjiuwen_runtime_foundation-*.whl` 或 `openjiuwen_runtime_service-*.whl`：`400`，说明需要先按当前仓库构建基础包。用通配符判断，不把版本号写死为 `0.1.0`。这一步放在调用部署器之前，避免缺包时要等到进程退出才返回 `500`。
5. 生成 `deployment_id`。把 WHL 保存到 `deploys/{deployment_id}/`，文件名沿用上传文件名。不要放到 `DIST_DIR`：`scripts/deploy_dev_server.sh` 启动时会清空该目录。
6. 端口规则与低码部署相同：未传则 `allocate_port`，传入但已被占用则 `400`。不要调用 `prepare_subprocess_deployment`，那个函数会改用低码 WHL。
7. 调用 `manager.deploy_agent`：
   - `name` 为模块路径
   - `version` 为请求中的业务版本，缺省 `1.0.0`
   - `user_id`、`space_id` 来自请求头
   - `mode` 为 `DeployMode.SUBPROCESS`
   - `extras` 包含 `whl_path`、`port`、`deployment_id`，以及 `data.base_whls`（第 4 步列出的基础包文件名）
   - 不传 `ir_path`
8. 返回 `201` 和部署结果。部署器失败时，与低码接口一样返回 `500`，`detail` 以 `Deployment failed` 开头。

部署器随后会：

1. 创建该部署的虚拟环境。
2. 安装 `DIST_DIR` 中当前存在的 `openjiuwen_*.whl`。
3. 安装本次上传的 WHL。
4. 执行 `python -m <name> --host 0.0.0.0 --port <port>`。

## Agent 包约定

平台不改包内容，上传的 WHL 需要满足现有启动方式：

- 工程根目录有 `pyproject.toml`，用 `uv build` 打包。
- 代码位于 `openjiuwen_runtime/<包名>/`，该目录有 `__main__.py`，入口调用 `app.run()`。
- 业务实现在 `AgentApp` 的 `@app.query`。
- 上传时的 `name` 必须是 `openjiuwen_runtime.<包名>`。部署器不会从 WHL 文件名推断模块名。
- FastAPI、uvicorn、pydantic 写在 Agent 自己的依赖里。
- `openjiuwen-runtime-service`、`openjiuwen-runtime-foundation` 由 `DIST_DIR` 里的基础 WHL 提供，不要写进业务包的依赖，也不要打进业务包。这样仓库只改这两个包的内部实现时，业务 WHL 不用重打。
- 业务代码只使用当前 `AgentApp` 约定：`@app.init`、`@app.query`、`@app.shutdown`，以及 `/health`、`/query`、`/reset_conversation`。这些约定变了，业务包要按新约定重打后再部署。
- 直接 `import openjiuwen` 的核心库不在 `openjiuwen_*.whl` 这组基础包里。需要它的业务包在自己的 `pyproject.toml` 里声明，随业务 WHL 一起安装。核心库升级时重打业务包，再按下面的运行时更新重新部署。

## 运行时更新

更新分两种，处理方式不同。

### 只更新本仓库的基础包

`foundation`、`service`，以及 `DIST_DIR` 里其他 `openjiuwen_*.whl` 的源码变了，业务包不用重打。

1. 拉最新代码后执行 `scripts/deploy_dev_server.sh`，或至少清空并重建 `DIST_DIR`，再重启管理服务。`foundation` 和 `service` 要一起构建。`service` 依赖 `openjiuwen-runtime-foundation==0.1.0`，只换其中一个 wheel 时，安装可能转到索引上拉另一份。
2. 对需要跟上的高码部署调用 `DELETE /api/v1/agents/{deployment_id}`。删除会停进程并删掉 `.venv`。
3. 用原来的业务 WHL 再调 `POST /api/v1/agents/deploy-whl`。新部署使用新的 `deployment_id`、新的虚拟环境和当前 `DIST_DIR`。端口按本次请求重新分配。
4. 调用方改用新的 `deployment_id`。部署响应里的 `base_whls` 是这次装进去的基础包文件名，用来核对这次部署对应哪一次构建。版本号仍是 `0.1.0` 时，文件名相同不表示内容相同，以重新部署的时间为准。

已经在跑的进程继续使用自己的 `.venv`。管理服务重启、`DIST_DIR` 被重建，都不会替换这些虚拟环境。`create_venv` 在目录还在时不会重装，同版本号再装一次也不能当作升级。

### 更新业务 WHL

业务代码或业务依赖变了，包括 `AgentApp` 约定变化后的重打、以及 `openjiuwen` 核心库版本变化：上传新的 WHL，走一次新的 `deploy-whl`。旧部署由调用方删除。两次部署的 `deployment_id` 不同。

## 二次开发与上游合并

二次开发只加上游仓库里没有的文件。上游 Runtime 更新后，把上游分支 merge 进来，再确认本模块仍挂在 `main.py` 末尾。

### 代码放哪里

| 内容 | 位置 |
| --- | --- |
| 高码部署、基础包检查、租户比对、静态页挂载 | 新文件 `server/openjiuwen_runtime/server/highcode_deploy.py` |
| 登录页和控制台 | 新目录 `highcode-console/`，React + Vite |
| 挂载 | `main.py` 文件末尾一行：`register_highcode(app, manager)` |
| 业务 Agent | 独立仓库，按「Agent 包约定」打包后上传 |

`register_highcode` 接收已经创建好的 `app` 和 `manager`。本模块不 `import main`，避免和 `main.py` 循环引用。端口分配调用 `foundation.port_utils`，部署调用现有 `manager.deploy_agent`、`get_deployment`、`delete_deployment`。

业务 Agent 不放进本仓库的 `applications/`、`service/`、`foundation/`、`management/`。这些目录属于上游，后续更新会整目录覆盖。本地 `server/.env` 不提交。

### 合并之后核对

merge 完成后只改 `highcode_deploy.py` 里对不上的调用，不把高码逻辑搬回上游函数。核对这四条仍成立：

1. `DeploymentManager.deploy_agent` 仍把 `name` 写入 `package_name`。
2. 不传 `ir_path` 时，子进程仍用 `package_name` 启动。
3. `MODE=dev` 仍先安装 `DIST_DIR` 下的 `openjiuwen_*.whl`，再安装 `whl_path`。
4. `AgentApp` 仍提供 `@app.init`、`@app.query`、`@app.shutdown` 和 `/health`、`/query`、`/reset_conversation`。这四条里的业务约定变了，重打业务 WHL 再部署。

`main.py` 冲突时保留上游内容，把 `register_highcode(app, manager)` 放回文件末尾。上游若已经在详情和删除里做了同等的租户比对，去掉本模块的中间件，只留部署路由。

## 错误

| 条件 | 状态码 |
| --- | --- |
| 不是 `subprocess`，或不是 `MODE=dev` | 400 |
| 文件不是 `.whl`，或内容为空 | 400 |
| `name` 为空或不是合法模块路径 | 400 |
| `DIST_DIR` 缺少 foundation 或 service 的 wheel | 400 |
| 指定端口已被占用 | 400 |
| 部署器启动失败 | 500 |
| 详情或删除时部署不存在，或租户不匹配 | 404 |

## 不做

- 不把高码逻辑写进 `main.py` 已有的部署、查询、删除函数。上游文件只增加 `register_highcode(app, manager)` 这一处调用。
- 不修改 `POST /api/v1/agents/deploy`，低码仍上传 `ir.json`。
- 不修改 `foundation`、`management`、`service`、`applications`、`cli`、`scripts/deploy_dev_server.sh`，也不改这些包的 `pyproject.toml`。
- 不修改子进程部署器。因此 `MODE=product` 仍安装 `lowcode-agent-runner`，本接口直接拒绝。`lowcode_agent_runner-*.whl` 和 `openjiuwen-*.whl` 仍然不会装进高码虚拟环境。
- 不支持 Docker、K8s 部署高码 WHL。
- 不把 `require_tenant` 改为 `True`。
- 不在本功能中实现按部署 ID 转发对话。
- 不解析 WHL 元数据，不根据文件名生成模块路径，也不比较基础包版本是否互相匹配。
- 不在业务 WHL 中捆绑 Runtime 基础包。
- 不提供原地升级，不保留原 `deployment_id`，不在已有 `.venv` 上热更新基础包。
- 不回收删除后留在 `deploys/{deployment_id}/` 里的业务 WHL。`.venv` 仍由现有 `stop` 删除。
- 不把 `highcode-console/` 放进上游目录，不改上游已有页面。
- 登录页不对接外部账号，不校验编码是否在外部系统存在。编码由使用人填写，并原样写入 `user_id`、`space_id`。
- 不改 `GET /api/v1/agents`。控制台用两次请求分别取出该用户和该组的部署。
