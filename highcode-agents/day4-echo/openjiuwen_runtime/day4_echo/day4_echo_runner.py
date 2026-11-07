#!/usr/bin/env python
# coding: utf-8
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved

"""
day4_echo - 空白 Agent 模板

运行方式:
    python -m openjiuwen_runtime.day4_echo --port 8090
"""

from typing import AsyncIterator, Tuple

from openjiuwen_runtime.service.app.agent_app import AgentApp

app = AgentApp(
    app_name="day4_echo",
    app_description="Day4 高码回显 Agent（empty 模板）",
    version="0.1.0",
)


@app.init
async def init():
    print("day4_echo 初始化完成!")


@app.query
async def query(msgs, request, cancel_event=None) -> AsyncIterator[Tuple[dict, bool]]:
    """处理查询请求"""
    last_user_msg = None
    for msg in reversed(msgs or []):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break

    if not last_user_msg:
        yield {"type": "text", "content": "请输入您的问题"}, True
        return

    reply = f"收到：{last_user_msg}"
    yield {"type": "text_delta", "content": reply}, False
    yield {"type": "result", "content": reply}, True


@app.shutdown
async def shutdown():
    print("day4_echo 关闭")


if __name__ == "__main__":
    app.run()
