#!/usr/bin/env bash
# 内网二次开发常用命令（默认离线，不访问互联网）
# 用法: bash 内网部署/常用命令.sh
#
# 第三方包请先在有网机器执行 下载第三方依赖.sh，把 wheels/ 拷到本目录后再用本脚本安装。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -L)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd -L)"
WHEEL_DIR="${WHEEL_DIR:-${SCRIPT_DIR}/wheels}"
# 仅使用本地 wheel，禁止访问 PyPI
OFFLINE_PIP=(--no-index --find-links="${WHEEL_DIR}")

cd "${PROJECT_ROOT}"

pause() {
    echo
    read -r -p "按回车继续..." _
}

ensure_wheels() {
    if [[ ! -d "${WHEEL_DIR}" ]] || [[ -z "$(ls -A "${WHEEL_DIR}"/*.whl 2>/dev/null || true)" ]]; then
        echo "离线包目录为空: ${WHEEL_DIR}"
        echo "请在有网机器执行: bash 内网部署/下载第三方依赖.sh"
        echo "再把生成的 wheels/ 目录拷到本机 ${SCRIPT_DIR}/ 下。"
        return 1
    fi
}

ensure_server_env() {
    if [[ ! -f "${PROJECT_ROOT}/server/.env" ]]; then
        echo "缺少 server/.env，请先按配置说明准备环境文件。"
        return 1
    fi
}

ensure_venv() {
    local dir="$1"
    cd "${dir}"
    [[ -d .venv ]] || uv venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
}

# 1. 离线安装管理服务依赖
install_server_deps() {
    ensure_wheels
    ensure_server_env
    ensure_venv "${PROJECT_ROOT}/server"

    if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
        uv pip install "${OFFLINE_PIP[@]}" -r "${SCRIPT_DIR}/requirements.txt"
    else
        uv pip install "${OFFLINE_PIP[@]}" "${WHEEL_DIR}"/*.whl
    fi
    # 本仓库源码包本地安装，不走网络
    uv pip install --no-deps -e ../foundation
    uv pip install --no-deps -e ../management
    uv pip install --no-deps -e .
    echo "管理服务依赖安装完成: ${PROJECT_ROOT}/server/.venv"
}

# 2. 构建 foundation / service 基础 WHL 到 dist/
build_base_whls() {
    ensure_wheels
    local dist_dir="${PROJECT_ROOT}/dist"
    mkdir -p "${dist_dir}"
    rm -f "${dist_dir}"/openjiuwen_runtime_foundation-*.whl
    rm -f "${dist_dir}"/openjiuwen_runtime_service-*.whl

    # 构建工具也从离线包取
    ensure_venv "${PROJECT_ROOT}/server"
    uv pip install "${OFFLINE_PIP[@]}" build setuptools wheel 2>/dev/null || true

    cd "${PROJECT_ROOT}/foundation"
    python -m build --wheel --outdir "${dist_dir}"

    cd "${PROJECT_ROOT}/service"
    python -m build --wheel --outdir "${dist_dir}"

    echo "基础 WHL 已输出到 ${dist_dir}:"
    ls -1 "${dist_dir}"/openjiuwen_runtime_*.whl 2>/dev/null || true
}

# 3. 启动管理服务
start_server() {
    ensure_server_env
    cd "${PROJECT_ROOT}/server"
    if [[ ! -d .venv ]]; then
        echo "未找到 server/.venv，请先执行菜单 1 安装依赖"
        return 1
    fi
    # shellcheck disable=SC1091
    source .venv/bin/activate
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
    echo "启动管理服务，控制台: http://127.0.0.1:8186/highcode/login"
    python -m openjiuwen_runtime.server.main
}

# 4. 打包高码 Agent 为 WHL（纯本地构建，不拉依赖）
build_highcode_whl() {
    ensure_wheels
    local agents_dir="${PROJECT_ROOT}/highcode-agents"
    local out_dir="${PROJECT_ROOT}/highcode-whls"
    mkdir -p "${out_dir}"

    ensure_venv "${PROJECT_ROOT}/server"
    uv pip install "${OFFLINE_PIP[@]}" build setuptools wheel 2>/dev/null || true

    echo "可选高码 Agent 目录:"
    local -a agents=()
    local i=1
    local name
    for name in "${agents_dir}"/*; do
        [[ -d "${name}" ]] || continue
        [[ -f "${name}/pyproject.toml" ]] || continue
        agents+=("$(basename "${name}")")
        echo "  ${i}) $(basename "${name}")"
        i=$((i + 1))
    done
    if [[ ${#agents[@]} -eq 0 ]]; then
        echo "未找到 highcode-agents/*/pyproject.toml"
        return 1
    fi

    local choice
    read -r -p "请选择编号 [1]: " choice
    choice="${choice:-1}"
    if ! [[ "${choice}" =~ ^[0-9]+$ ]] || [[ "${choice}" -lt 1 ]] || [[ "${choice}" -gt ${#agents[@]} ]]; then
        echo "无效选择"
        return 1
    fi

    local agent="${agents[$((choice - 1))]}"
    cd "${agents_dir}/${agent}"
    python -m build --wheel --outdir "${out_dir}"
    echo "已打包到 ${out_dir}:"
    ls -1t "${out_dir}"/*.whl | head -5
}

# 5. 构建高码控制台前端（需已有 node_modules，不访问 npm 仓库）
build_highcode_console() {
    cd "${PROJECT_ROOT}/highcode-console"
    if [[ ! -d node_modules ]]; then
        echo "缺少 highcode-console/node_modules"
        echo "请在有网机器执行 npm install 后，把整个 highcode-console/node_modules 拷入内网。"
        return 1
    fi
    npm run build --offline
    echo "控制台已构建: ${PROJECT_ROOT}/highcode-console/dist"
}

# 6. 本地自测启动高码 Agent（示例 day4-echo）
run_highcode_local() {
    ensure_wheels
    local agent_dir="${PROJECT_ROOT}/highcode-agents/day4-echo"
    local port="${1:-8090}"
    if [[ ! -d "${agent_dir}" ]]; then
        echo "未找到 ${agent_dir}"
        return 1
    fi
    ensure_venv "${agent_dir}"
    uv pip install "${OFFLINE_PIP[@]}" -r "${SCRIPT_DIR}/requirements.txt" 2>/dev/null \
        || uv pip install "${OFFLINE_PIP[@]}" "${WHEEL_DIR}"/*.whl
    uv pip install --no-deps -e ../../foundation -e ../../service -e .
    echo "本地启动: http://127.0.0.1:${port}/query"
    python -m openjiuwen_runtime.day4_echo --port "${port}"
}

show_menu() {
    local wheel_status="无"
    if [[ -d "${WHEEL_DIR}" ]] && ls "${WHEEL_DIR}"/*.whl >/dev/null 2>&1; then
        wheel_status="已就绪 ($(ls -1 "${WHEEL_DIR}"/*.whl | wc -l | tr -d ' ') 个 whl)"
    fi
    cat <<EOF

========================================
  agent-runtime 内网常用命令（离线）
  项目根目录: ${PROJECT_ROOT}
  离线包目录: ${WHEEL_DIR}  [${wheel_status}]
========================================
  1) 离线安装管理服务依赖
  2) 构建 foundation/service 基础 WHL -> dist/
  3) 启动管理服务 (8186)
  4) 打包高码 Agent 为 WHL -> highcode-whls/
  5) 构建高码控制台前端（需已有 node_modules）
  6) 本地自测启动 day4-echo (8090)
  0) 退出
========================================
EOF
}

main() {
    while true; do
        show_menu
        local opt
        read -r -p "请选择: " opt
        case "${opt}" in
            1) install_server_deps; pause ;;
            2) build_base_whls; pause ;;
            3) start_server ;;
            4) build_highcode_whl; pause ;;
            5) build_highcode_console; pause ;;
            6) run_highcode_local ;;
            0) echo "退出"; exit 0 ;;
            *) echo "无效选项: ${opt}"; pause ;;
        esac
    done
}

main "$@"
