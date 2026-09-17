"""E2E 测试通用 fixtures — 页面错误监控

运行方式：
  - 默认无头模式（可息屏后台执行）：pytest tests/e2e/ -v
  - 有头模式（可看到浏览器）：pytest tests/e2e/ -v --headed
"""

import os
import pytest
from typing import Generator, Dict, List, Any
from playwright.sync_api import Page, BrowserContext


# Force Playwright to use old headless mode (avoid chromium_headless_shell)
os.environ["PLAYWRIGHT_CHROMIUM_USE_HEADLESS_NEW"] = "0"


@pytest.fixture(scope="session")
def browser_context_args(request):
    """配置浏览器上下文参数"""
    headed = request.config.getoption("--headed")
    args = {
        "viewport": {"width": 1920, "height": 1080},
    }
    # 有头模式下录制视频
    if headed:
        args["record_video_size"] = {"width": 1920, "height": 1080}
    return args


@pytest.fixture(scope="session")
def browser_type_launch_args(request):
    """配置浏览器启动参数"""
    chromium_path = r"C:\Users\weijinshu\AppData\Local\ms-playwright\chromium-1234\chrome-win64\chrome.exe"
    headed = request.config.getoption("--headed")
    return {
        "executable_path": chromium_path,
        "headless": not headed,  # 默认无头，--headed 时有头
    }


@pytest.fixture(scope="function")
def error_collector(page: Page) -> Generator[Dict[str, List[Any]], None, None]:
    """
    收集页面所有类型的错误：
    - console_errors: console.error / console.warn
    - page_errors: 未捕获的 JS 异常
    - failed_requests: 网络请求失败（DNS、超时、CORS 等）
    - resource_errors: HTTP 4xx/5xx 资源加载
    """
    errors: Dict[str, List[Any]] = {
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "resource_errors": [],
    }

    def on_console(msg):
        if msg.type == "error":
            errors["console_errors"].append({
                "type": msg.type,
                "text": msg.text,
                "location": f"{msg.location.get('url', '')}:{msg.location.get('lineNumber', '')}",
            })

    def on_pageerror(err):
        errors["page_errors"].append(str(err))

    def on_requestfailed(req):
        errors["failed_requests"].append({
            "url": req.url,
            "failure": req.failure,
            "method": req.method,
        })

    def on_requestfinished(req):
        try:
            resp = req.response()
        except Exception:
            resp = None
        if resp and resp.status >= 400:
            errors["resource_errors"].append({
                "url": req.url,
                "status": resp.status,
                "method": req.method,
            })

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("requestfailed", on_requestfailed)
    page.on("requestfinished", on_requestfinished)

    yield errors

    # 清理监听器
    page.remove_listener("console", on_console)
    page.remove_listener("pageerror", on_pageerror)
    page.remove_listener("requestfailed", on_requestfailed)
    page.remove_listener("requestfinished", on_requestfinished)
