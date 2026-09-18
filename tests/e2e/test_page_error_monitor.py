"""方案1：页面级错误监控测试

模拟用户访问页面，每个页面只打开一次，一次性检测：
- 控制台错误（console.error）
- JS 异常（pageerror）
- 网络请求失败（requestfailed）
- 资源加载错误（4xx/5xx）
- 白屏检测
- 标题验证
"""

import json
import os
import time
import pytest
from playwright.sync_api import Page

from .conftest import error_collector  # noqa: F401

# 报告输出目录
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


# ============== 已知可忽略的 console 错误（网站自身问题，不影响功能） ==============
KNOWN_CONSOLE_ERROR_PATTERNS = [
    "Hydration completed but contains mismatches",  # Vue/Nuxt SSR 水合不匹配
    "sensors",  # 神策分析 SDK 配置相关
    "Failed to load resource: the server responded with a status of 503",  # 第三方分析服务 event.anycubic.com
    "Failed to load resource: the server responded with a status of 401",  # 需登录的接口
    "google-analytics.com",  # Google Analytics 被网络拦截
    "ERR_ABORTED",  # 请求被中止（通常是广告/统计脚本）
    "event.anycubic.com",  # 埋点服务被浏览器拦截
]


# ============== 测试目标页面 ==============
TARGET_PAGES = {
    # AIGC 模块
    "AIGC首页": "https://www.makeronline.com/zh/aigc/",
    "图片生成": "https://www.makeronline.com/zh/aigc/tools?tab=image&from=home",
    "3D模型生成": "https://www.makeronline.com/zh/aigc/tools?tab=model&from=home",
    "多色打印": "https://www.makeronline.com/zh/aigc/tools?tab=color&from=home",
    "资产中心": "https://www.makeronline.com/zh/aigc/assets",
    "热门玩法": "https://www.makeronline.com/zh/aigc/trending",
    # 主站公共页面
    "主站首页(EN)": "https://www.makeronline.com/en/",
    "模型库": "https://www.makeronline.com/en/allModel/all/all/0.html",
    "比赛列表": "https://www.makeronline.com/en/contestList",
    "活动详情": "https://www.makeronline.com/en/yourStory/activity-details",
    "模型搜索": "https://www.makeronline.com/en/search/modelList",
    "积分规则": "https://www.makeronline.com/en/points/rules.html",
    "模型详情": "https://www.makeronline.com/en/model/Minecraft%20Tic-Tac-Toe%20-%20XL%20version/327868.html?trackModuleType=1",
    "个人中心": "https://www.makeronline.com/en/user/personalInfo/9ae2ceea-75fc-4930-a2bd-5b30d9ac7df0.html",
    "比赛详情": "https://www.makeronline.com/en/contest/military-model-design-contest/201.html?trackContestType=3",
    "抽奖": "https://www.makeronline.com/en/drawLottery",
    # 论坛
    "论坛首页": "https://forum.makeronline.com/en/",
}


def _is_known_error(error_text: str) -> bool:
    """检查是否为已知可忽略的错误"""
    return any(pattern in error_text for pattern in KNOWN_CONSOLE_ERROR_PATTERNS)


# 已知可忽略的外部服务 URL 模式
KNOWN_EXTERNAL_URL_PATTERNS = [
    "google-analytics.com",
    "event.anycubic.com",
    "facebook.com",
    "doubleclick.net",
    "/api/activity/prize-list",  # 抽奖页奖品列表接口，需登录
    "cdn-acop.makeronline.com",  # CDN 资源被浏览器 ORB 拦截
]


def _is_known_external_url(url: str) -> bool:
    """检查是否为已知可忽略的外部服务请求"""
    return any(pattern in url for pattern in KNOWN_EXTERNAL_URL_PATTERNS)


@pytest.mark.UI
@pytest.mark.P0
class TestPageErrorMonitor:
    """方案1：所有页面在一个标签页内顺序检测，避免多窗口"""

    def test_all_pages_health_check(self, page: Page, error_collector):
        """
        在一个标签页内顺序访问所有页面，每个页面只访问一次，
        一次性检测全部维度：
        1. HTTP 200
        2. 非白屏
        3. 标题有效
        4. 无 console.error
        5. 无 JS 异常
        6. 无请求失败
        7. 无资源 4xx/5xx
        """
        all_issues = {}  # page_name -> list of issues
        page_timings = {}  # page_name -> {"load_ms": x, "render_ms": y}

        for page_name, page_url in TARGET_PAGES.items():
            # 清空上一轮的错误收集
            for key in error_collector:
                error_collector[key].clear()

            # 访问页面，分别记录网络加载和渲染稳定耗时
            t0 = time.perf_counter()
            response = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
            t1 = time.perf_counter()
            load_ms = (t1 - t0) * 1000

            page.wait_for_timeout(5000)  # 等待 SPA 渲染 + 初始请求完成
            t2 = time.perf_counter()
            render_ms = (t2 - t1) * 1000

            page_timings[page_name] = {"load_ms": round(load_ms, 2), "render_ms": round(render_ms, 2)}

            issues = []

            # 1. HTTP 状态码
            if response.status != 200:
                issues.append(f"HTTP 状态码: {response.status} (期望 200)")

            # 2. 白屏检测
            body_text = page.evaluate("() => document.body.innerText")
            if len(body_text) <= 50:
                issues.append(f"页面可能白屏，body 文本长度仅 {len(body_text)}")

            # 3. 标题检查（大小写不敏感）
            title = page.title()
            title_lower = title.lower()
            if not title:
                issues.append("页面标题为空")
            elif "anycubic" not in title_lower and "ai" not in title_lower and "makeronline" not in title_lower and "model" not in title_lower and "contest" not in title_lower:
                issues.append(f"页面标题异常: {title}")

            # 4. 控制台错误（过滤已知可忽略的错误）
            real_console_errors = [
                e for e in error_collector["console_errors"]
                if not _is_known_error(e["text"])
            ]
            if real_console_errors:
                for e in real_console_errors[:5]:
                    issues.append(f"Console [{e['type']}]: {e['text'][:120]}")

            # 5. JS 异常
            if error_collector["page_errors"]:
                for e in error_collector["page_errors"][:5]:
                    issues.append(f"JS异常: {e[:120]}")

            # 6. 请求失败（过滤已知外部服务）
            real_failed = [e for e in error_collector["failed_requests"] if not _is_known_external_url(e["url"])]
            if real_failed:
                for e in real_failed[:5]:
                    issues.append(f"请求失败: {e['url'][:80]} → {e['failure']}")

            # 7. 资源错误（过滤已知外部服务）
            real_resource = [e for e in error_collector["resource_errors"] if not _is_known_external_url(e["url"])]
            if real_resource:
                for e in real_resource[:5]:
                    issues.append(f"资源错误: HTTP {e['status']} - {e['url'][:80]}")

            if issues:
                all_issues[page_name] = issues

        # 打印汇总
        print(f"\n{'=' * 60}")
        print(f"{'页面':<12} {'状态':<6} {'网络加载':>10} {'渲染稳定':>10} {'总耗时':>10}")
        print(f"{'=' * 60}")
        for name in TARGET_PAGES:
            timing = page_timings.get(name, {"load_ms": 0, "render_ms": 0})
            total = timing["load_ms"] + timing["render_ms"]
            if name in all_issues:
                print(f"  {name:<10} FAIL  {timing['load_ms']:>8.0f}ms {timing['render_ms']:>8.0f}ms {total:>8.0f}ms  ({len(all_issues[name])} 个问题)")
            else:
                print(f"  {name:<10} PASS  {timing['load_ms']:>8.0f}ms {timing['render_ms']:>8.0f}ms {total:>8.0f}ms")
        print(f"{'=' * 60}")

        # 生成报告
        from datetime import datetime
        report_data = {
            "report_time": datetime.now().isoformat(),
            "total_pages": len(TARGET_PAGES),
            "all_clean": len(all_issues) == 0,
            "pages": {
                name: {
                    "error_count": len(all_issues.get(name, [])),
                    "status": "FAIL" if name in all_issues else "PASS",
                    "load_ms": page_timings.get(name, {}).get("load_ms", 0),
                    "render_ms": page_timings.get(name, {}).get("render_ms", 0),
                    "total_ms": round(
                        page_timings.get(name, {}).get("load_ms", 0)
                        + page_timings.get(name, {}).get("render_ms", 0), 2
                    ),
                    "issues": all_issues.get(name, []),
                }
                for name in TARGET_PAGES
            },
        }
        report_path = os.path.join(REPORTS_DIR, "page_error_monitor_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"报告已保存: {report_path}")

        # 断言
        assert len(all_issues) == 0, (
            f"{len(all_issues)} 个页面存在问题:\n"
            + "\n".join(
                f"  [{name}] {len(issues)} 个问题:\n"
                + "\n".join(f"    - {issue}" for issue in issues)
                for name, issues in all_issues.items()
            )
        )
