# coding: utf-8
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved

"""高码 WHL 部署与控制台挂载。

部署、基础包检查、详情和删除的租户比对都在本文件。
main 只调用 register_highcode，避免二次开发改动散落到上游路由函数里。
"""

import re
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.staticfiles import StaticFiles

from openjiuwen_runtime.foundation.config import PROJECT_ROOT, settings
from openjiuwen_runtime.foundation.log import get_logger
from openjiuwen_runtime.foundation.port_utils import allocate_port, is_port_available
from openjiuwen_runtime.management.models.deployment_params import DeployAgentParams
from openjiuwen_runtime.management.models.enums import DeployMode

from .middleware.tenant import get_tenant_context

logger = get_logger(__name__)

# 本模块自己登记已分配端口，不共用 main 里的集合
_allocated_ports: set[int] = set()

_MODULE_NAME_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$"
)
_DEPLOYMENT_PATH_RE = re.compile(r"^/api/v1/agents/([^/]+)$")
_ASSET_SUFFIXES = {
    ".js",
    ".css",
    ".map",
    ".svg",
    ".png",
    ".ico",
    ".woff",
    ".woff2",
    ".json",
    ".txt",
    ".webp",
}

_CONSOLE_DIST = PROJECT_ROOT / "highcode-console" / "dist"


def _not_found(deployment_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"Deployment {deployment_id} not found"},
    )


class HighcodeTenantGuardMiddleware(BaseHTTPMiddleware):
    """详情和删除的租户比对。

    挂在 TenantContextMiddleware 外侧，先于它执行，因此直接读请求头。
    只处理 GET、DELETE /api/v1/agents/{deployment_id}。
    """

    def __init__(self, app, deployment_manager):
        super().__init__(app)
        self._manager = deployment_manager

    async def dispatch(self, request: Request, call_next):
        if request.method not in {"GET", "DELETE"}:
            return await call_next(request)

        matched = _DEPLOYMENT_PATH_RE.match(request.url.path)
        if matched is None:
            return await call_next(request)

        deployment_id = matched.group(1)
        # 这两个路径虽然只有一段，但不是部署 ID
        if deployment_id in {"deploy", "deploy-whl"}:
            return await call_next(request)

        user_header = request.headers.get("X-User-ID")
        space_header = request.headers.get("X-Space-ID")
        if user_header is None and space_header is None:
            return await call_next(request)

        deployment = await self._manager.get_deployment(deployment_id)
        if deployment is None:
            return await call_next(request)

        if user_header is not None and user_header != deployment.user_id:
            return _not_found(deployment_id)
        if space_header is not None and space_header != deployment.space_id:
            return _not_found(deployment_id)
        return await call_next(request)


class HighcodeConsoleFiles(StaticFiles):
    """把 /highcode 下的前端路由回退到 index.html，静态资源仍按文件返回。"""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != status.HTTP_404_NOT_FOUND:
                raise
            if Path(path).suffix.lower() in _ASSET_SUFFIXES:
                raise
            return FileResponse(_CONSOLE_DIST / "index.html")
        if response.status_code == status.HTTP_404_NOT_FOUND:
            if Path(path).suffix.lower() in _ASSET_SUFFIXES:
                return response
            return FileResponse(_CONSOLE_DIST / "index.html")
        return response


def _ensure_subprocess_dev() -> None:
    if settings.DEPLOY_TYPE != "subprocess" or settings.MODE != "dev":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="高码 WHL 部署只支持子进程开发模式",
        )


def _validate_whl(filename: str | None, content: bytes) -> str:
    safe_name = Path(filename or "").name
    if not safe_name.endswith(".whl") or not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件不是 .whl，或内容为空",
        )
    return safe_name


def _validate_module_name(name: str) -> str:
    module_name = (name or "").strip()
    if not _MODULE_NAME_RE.fullmatch(module_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="name 为空或不是合法模块路径",
        )
    return module_name


def _list_base_wheels() -> list[str]:
    dist_path = settings.dist_path
    foundation_exists = any(dist_path.glob("openjiuwen_runtime_foundation-*.whl"))
    service_exists = any(dist_path.glob("openjiuwen_runtime_service-*.whl"))
    if not foundation_exists or not service_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DIST_DIR 缺少 openjiuwen_runtime_foundation 或 openjiuwen_runtime_service 的 wheel，请先按当前仓库构建基础包",
        )
    return [path.name for path in sorted(dist_path.glob("openjiuwen_*.whl"))]


def _resolve_port(raw_port: str) -> int:
    text = (raw_port or "").strip()
    if not text:
        port = allocate_port(exclude_ports=_allocated_ports)
        _allocated_ports.add(port)
        logger.info("Auto-allocated port: %s", port)
        return port

    try:
        port = int(text)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"端口 {text} 不合法",
        ) from None

    if port < 1 or port > 65535 or port in _allocated_ports or not is_port_available(port):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"端口 {port} 已被占用",
        )
    _allocated_ports.add(port)
    logger.info("Port: %s", port)
    return port


def _query_targets(base_url: str) -> list[str]:
    """先用部署记录里的地址，连不上时再改用 127.0.0.1 同端口。"""
    root = base_url.rstrip("/")
    targets = [f"{root}/query"]
    parsed = urlparse(root)
    host = parsed.hostname
    if host and host not in {"127.0.0.1", "localhost", "::1"} and parsed.port:
        loopback = urlunparse(parsed._replace(netloc=f"127.0.0.1:{parsed.port}"))
        targets.append(f"{loopback.rstrip('/')}/query")
    return targets


async def _open_agent_query(targets: list[str], body: bytes, content_type: str):
    """按顺序连接 Agent 的 /query，返回已建立的流式响应和客户端。"""
    client = httpx.AsyncClient(timeout=None)
    last_error = None
    for target in targets:
        try:
            request = client.build_request(
                "POST",
                target,
                content=body,
                headers={"Content-Type": content_type or "application/json"},
            )
            response = await client.send(request, stream=True)
            return client, response
        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning("Agent query connect failed: %s, error=%s", target, exc)
    await client.aclose()
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"无法连接智能体: {last_error}",
    )


def register_highcode(app: FastAPI, deployment_manager) -> None:
    """挂上高码部署路由、租户比对中间件和控制台静态页。"""

    @app.post("/api/v1/agents/deploy-whl")
    async def deploy_whl(
        request: Request,
        file: UploadFile = File(...),
        name: str = Form(...),
        version: str = Form("1.0.0"),
        port: str = Form(""),
    ):
        """上传高码 Agent 的 WHL 并按子进程方式部署。"""
        _ensure_subprocess_dev()
        content = await file.read()
        whl_name = _validate_whl(file.filename, content)
        module_name = _validate_module_name(name)
        base_whls = _list_base_wheels()
        chosen_port = _resolve_port(port)

        deployment_id = str(uuid.uuid4())
        deploy_dir = settings.deploy_path / deployment_id
        deploy_dir.mkdir(parents=True, exist_ok=True)
        whl_path = deploy_dir / whl_name
        whl_path.write_bytes(content)

        user_id, space_id = get_tenant_context(request)
        package_version = version.strip() if version and version.strip() else "1.0.0"
        logger.info(
            "Received highcode deploy: user_id=%s, space_id=%s, name=%s, whl=%s",
            user_id,
            space_id,
            module_name,
            whl_name,
        )

        try:
            result = await deployment_manager.deploy_agent(
                DeployAgentParams(
                    name=module_name,
                    version=package_version,
                    user_id=user_id,
                    space_id=space_id,
                    mode=DeployMode.SUBPROCESS,
                    extras={
                        "whl_path": str(whl_path),
                        "port": chosen_port,
                        "deployment_id": deployment_id,
                        "data": {"base_whls": base_whls},
                    },
                )
            )
        except Exception as exc:
            logger.exception("Highcode agent deployment failed")
            detail = str(exc)
            if not detail.startswith("Deployment failed"):
                detail = f"Deployment failed: {detail}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=detail,
            ) from exc

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "deployment_id": deployment_id,
                "type": result.deployment_type.value,
                "name": result.name,
                "status": result.deployment_status.value,
                "url": result.url,
                "base_whls": base_whls,
            },
        )

    @app.post("/api/v1/agents/{deployment_id}/query")
    async def query_agent(deployment_id: str, request: Request):
        """把控制台的测试请求原样转发到对应 Agent 的 /query。"""
        deployment = await deployment_manager.get_deployment(deployment_id)
        if deployment is None:
            return _not_found(deployment_id)
        if deployment.deployment_status.value != "running" or not deployment.url:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="部署未就绪",
            )

        body = await request.body()
        content_type = request.headers.get("Content-Type", "application/json")
        client, upstream = await _open_agent_query(
            _query_targets(deployment.url),
            body,
            content_type,
        )

        async def relay():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        media_type = upstream.headers.get("content-type", "text/event-stream")
        return StreamingResponse(
            relay(),
            status_code=upstream.status_code,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 后加的中间件在最外层，会先于 TenantContextMiddleware 执行
    app.add_middleware(HighcodeTenantGuardMiddleware, deployment_manager=deployment_manager)

    index_file = _CONSOLE_DIST / "index.html"
    if index_file.is_file():
        app.mount(
            "/highcode",
            HighcodeConsoleFiles(directory=str(_CONSOLE_DIST), html=True),
            name="highcode-console",
        )
        logger.info("Highcode console mounted from %s", _CONSOLE_DIST)
    else:
        logger.info("Highcode console dist not found, skip mount: %s", _CONSOLE_DIST)
