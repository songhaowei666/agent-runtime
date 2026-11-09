#!/usr/bin/env bash
# 根据项目根目录 requirements.txt 解析传递依赖，并下载到 内网部署/wheels/
# 不下载本仓库源码包（foundation / service / management / server 等），内网用源码安装。
#
# 默认按内网 Linux x86_64、Python 3.11 下载。目标机器不是这个平台时，先改下面两个变量。

set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
PYTHON_PLATFORM="${PYTHON_PLATFORM:-x86_64-manylinux2014}"
INDEX_URL="${INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
TRUSTED_HOST="${TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -L)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd -L)}"
OUT_DIR="${SCRIPT_DIR}/wheels"
ROOT_REQ="${PROJECT_ROOT}/requirements.txt"
REQ_IN="${SCRIPT_DIR}/requirements.in"
REQ_TXT="${SCRIPT_DIR}/requirements.txt"

if [[ ! -f "${ROOT_REQ}" ]]; then
    echo "未找到 ${ROOT_REQ}" >&2
    exit 1
fi

mkdir -p "${OUT_DIR}"

# 本仓库源码包不打进离线目录
rm -f \
    "${OUT_DIR}"/openjiuwen_runtime_foundation-*.whl \
    "${OUT_DIR}"/openjiuwen_runtime_management-*.whl \
    "${OUT_DIR}"/openjiuwen_runtime_service-*.whl \
    "${OUT_DIR}"/agent_runtime_server-*.whl \
    "${OUT_DIR}"/day4_echo_runner-*.whl \
    "${OUT_DIR}"/lowcode_agent_runner-*.whl

# 从根目录 requirements.txt 抽出可安装行（去掉注释和空行）
python3 - "${ROOT_REQ}" "${REQ_IN}" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
lines = []
for raw in src.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    lines.append(line)
dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"已写入直接依赖 {len(lines)} 条: {dst}")
PY

echo "解析传递依赖，平台 ${PYTHON_PLATFORM}，Python ${PYTHON_VERSION}"
uv pip compile \
    "${REQ_IN}" \
    -o "${REQ_TXT}" \
    --python-version "${PYTHON_VERSION}" \
    --python-platform "${PYTHON_PLATFORM}" \
    --default-index "${INDEX_URL}" \
    --allow-insecure-host "${TRUSTED_HOST}" \
    --no-header \
    --no-annotate

case "${PYTHON_PLATFORM}" in
    x86_64-manylinux2014) PIP_PLATFORM="manylinux2014_x86_64" ;;
    aarch64-manylinux2014) PIP_PLATFORM="manylinux2014_aarch64" ;;
    aarch64-apple-darwin) PIP_PLATFORM="macosx_11_0_arm64" ;;
    x86_64-apple-darwin) PIP_PLATFORM="macosx_10_12_x86_64" ;;
    *)
        echo "不支持的 PYTHON_PLATFORM: ${PYTHON_PLATFORM}" >&2
        exit 1
        ;;
esac

PY_TAG="${PYTHON_VERSION//./}"

echo "下载 wheel 到 ${OUT_DIR}"
python3 -m pip download \
    -r "${REQ_TXT}" \
    -d "${OUT_DIR}" \
    --no-deps \
    -i "${INDEX_URL}" \
    --trusted-host "${TRUSTED_HOST}" \
    --python-version "${PY_TAG}" \
    --platform "${PIP_PLATFORM}" \
    --implementation cp \
    --abi "cp${PY_TAG}" \
    --only-binary=:all:

echo "完成。第三方 wheel 在 ${OUT_DIR}，锁定清单在 ${REQ_TXT}"
echo "说明: openjiuwen 若源站无 whl，需另行准备后放入 ${OUT_DIR}"
