"""方案2：批量页面巡检测试

定义所有需要巡检的页面 URL 列表，在一个标签页内逐个访问并检测：
- HTTP 状态码
- 页面标题
- 控制台错误
- JS 异常
- 请求失败
- 资源加载错误
- 白屏检测
- 关键元素存在性
生成巡检汇总报告。
"""

import json
import os
import time
import pytest
from datetime import datetime
from typing import Dict, List, Any
from playwright.sync_api import Page

from .conftest import error_collector  # noqa: F401

# 报告输出目录
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


# ============== 已知可忽略的 console 错误（网站自身问题，不影响功能） ==============
KNOWN_CONSOLE_ERROR_PATTERNS = [
    "Hydration completed but contains mismatches",  # Vue/Nuxt SSR 水合不匹配
    "sensors",  # 神策分析 SDK 配置相关
    "Failed to load resource: the server responded with a status of 503",  # 第三方分析服务
    "Failed to load resource: the server responded with a status of 401",  # 需登录的接口
    "google-analytics.com",  # Google Analytics 被网络拦截
    "ERR_ABORTED",  # 请求被中止
]


# 已知可忽略的外部服务 URL 模式
KNOWN_EXTERNAL_URL_PATTERNS = [
    "google-analytics.com",
    "event.anycubic.com",
    "facebook.com",
    "doubleclick.net",
    "/api/activity/prize-list",  # 抽奖页奖品列表接口，需登录
]


def _is_known_error(error_text: str) -> bool:
    """检查是否为已知可忽略的错误"""
    return any(pattern in error_text for pattern in KNOWN_CONSOLE_ERROR_PATTERNS)


def _is_known_external_url(url: str) -> bool:
    """检查是否为已知可忽略的外部服务请求"""
    return any(pattern in url for pattern in KNOWN_EXTERNAL_URL_PATTERNS)


# ============== 巡检页面清单 ==============
INSPECTION_PAGES: List[Dict[str, Any]] = [
    # -------- AIGC 模块 --------
    {
        "name": "AIGC首页",
        "url": "https://www.makeronline.com/zh/aigc/",
        "expected_title_keywords": ["Anycubic"],
        "expected_elements": ["AI"],
    },
    {
        "name": "图片生成",
        "url": "https://www.makeronline.com/zh/aigc/tools?tab=image&from=home",
        "expected_title_keywords": ["Anycubic"],
        "expected_elements": [],
        "skip_blank_check": True,
    },
    {
        "name": "3D模型生成",
        "url": "https://www.makeronline.com/zh/aigc/tools?tab=model&from=home",
        "expected_title_keywords": ["Anycubic"],
        "expected_elements": [],
    },
    {
        "name": "多色打印",
        "url": "https://www.makeronline.com/zh/aigc/tools?tab=color&from=home",
        "expected_title_keywords": ["Anycubic"],
        "expected_elements": [],
    },
    {
        "name": "资产中心",
        "url": "https://www.makeronline.com/zh/aigc/assets",
        "expected_title_keywords": ["Anycubic"],
        "expected_elements": [],
    },
    {
        "name": "热门玩法",
        "url": "https://www.makeronline.com/zh/aigc/trending",
        "expected_title_keywords": ["Anycubic"],
        "expected_elements": ["玩法"],
    },
    # -------- 主站公共页面 --------
    {
        "name": "主站首页(EN)",
        "url": "https://www.makeronline.com/en/",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
        "skip_blank_check": True,
    },
    {
        "name": "模型库",
        "url": "https://www.makeronline.com/en/allModel/all/all/0.html",
        "expected_title_keywords": [],  # 标题是 "All Models"，不含 Makeronline
        "expected_elements": [],
    },
    {
        "name": "比赛列表",
        "url": "https://www.makeronline.com/en/contestList",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
    },
    {
        "name": "活动详情",
        "url": "https://www.makeronline.com/en/yourStory/activity-details",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
    },
    {
        "name": "模型搜索",
        "url": "https://www.makeronline.com/en/search/modelList",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
    },
    {
        "name": "积分规则",
        "url": "https://www.makeronline.com/en/points/rules.html",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
    },
    {
        "name": "模型详情",
        "url": "https://www.makeronline.com/en/model/Minecraft%20Tic-Tac-Toe%20-%20XL%20version/327868.html?trackModuleType=1",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
    },
    {
        "name": "个人中心",
        "url": "https://www.makeronline.com/en/user/personalInfo/9ae2ceea-75fc-4930-a2bd-5b30d9ac7df0.html",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
        "skip_blank_check": True,  # 需登录
    },
    {
        "name": "比赛详情",
        "url": "https://www.makeronline.com/en/contest/military-model-design-contest/201.html?trackContestType=3",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
    },
    {
        "name": "抽奖",
        "url": "https://www.makeronline.com/en/drawLottery",
        "expected_title_keywords": ["Makeronline"],
        "expected_elements": [],
    },
    # -------- 论坛 --------
    {
        "name": "论坛首页",
        "url": "https://forum.makeronline.com/en/",
        "expected_title_keywords": [],  # 论坛标题格式不同，只检测非空
        "expected_elements": [],
        "skip_blank_check": True,
    },
]


@pytest.mark.UI
@pytest.mark.P0
class TestPageInspection:
    """方案2：批量页面巡检 — 一个标签页内顺序检测所有页面"""

    def test_batch_inspection(self, page: Page, error_collector):
        """
        在一个标签页内顺序访问所有页面，每个页面只访问一次，
        对每个页面执行全量巡检：
        1. HTTP 状态码 = 200
        2. 页面标题非空且包含预期关键词
        3. 无控制台错误
        4. 无 JS 异常
        5. 无请求失败
        6. 无资源加载错误(4xx/5xx)
        7. 非白屏
        8. 关键页面元素存在
        """
        results: List[Dict[str, Any]] = []
        all_issues: Dict[str, List[str]] = {}

        for page_info in INSPECTION_PAGES:
            page_name = page_info["name"]
            page_url = page_info["url"]
            issues: List[str] = []

            # 清空上一轮的错误收集
            for key in error_collector:
                error_collector[key].clear()

            # 访问页面，分别记录网络加载和渲染稳定耗时
            t0 = time.perf_counter()
            response = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
            t1 = time.perf_counter()
            load_ms = (t1 - t0) * 1000

            page.wait_for_timeout(5000)  # 等待页面稳定
            t2 = time.perf_counter()
            render_ms = (t2 - t1) * 1000

            # 1. HTTP 状态码检查
            http_ok = response.status == 200
            if not http_ok:
                issues.append(f"HTTP 状态码: {response.status} (期望 200)")

            # 2. 页面标题检查
            title = page.title()
            title_ok = len(title) > 0
            if not title_ok:
                issues.append("页面标题为空")
            else:
                for keyword in page_info.get("expected_title_keywords", []):
                    if keyword not in title:
                        issues.append(f"标题缺少关键词 '{keyword}'，实际: {title}")

            # 3. 控制台错误检查（过滤已知可忽略的错误）
            real_console_errors = [
                e for e in error_collector["console_errors"]
                if not _is_known_error(e["text"])
            ]
            console_ok = len(real_console_errors) == 0
            if not console_ok:
                for e in real_console_errors[:5]:
                    issues.append(f"控制台错误: [{e['type']}] {e['text'][:100]}")

            # 4. JS 异常检查
            js_ok = len(error_collector["page_errors"]) == 0
            if not js_ok:
                for e in error_collector["page_errors"][:5]:
                    issues.append(f"JS 异常: {e[:100]}")

            # 5. 请求失败检查（过滤已知外部服务）
            real_failed = [e for e in error_collector["failed_requests"] if not _is_known_external_url(e["url"])]
            request_ok = len(real_failed) == 0
            if not request_ok:
                for e in real_failed[:5]:
                    issues.append(f"请求失败: {e['url'][:80]} → {e['failure']}")

            # 6. 资源加载错误检查（过滤已知外部服务）
            real_resource = [e for e in error_collector["resource_errors"] if not _is_known_external_url(e["url"])]
            resource_ok = len(real_resource) == 0
            if not resource_ok:
                for e in real_resource[:5]:
                    issues.append(f"资源错误: HTTP {e['status']} - {e['url'][:80]}")

            # 7. 白屏检测（部分页面可跳过）
            body_text = page.evaluate("() => document.body.innerText")
            skip_blank = page_info.get("skip_blank_check", False)
            not_blank = skip_blank or len(body_text) > 50
            if not not_blank:
                issues.append(f"页面可能白屏，body 文本长度仅 {len(body_text)}")

            # 8. 关键元素存在性检查
            elements_ok = True
            for element_text in page_info.get("expected_elements", []):
                found = page.evaluate(
                    f"() => document.body.innerText.includes('{element_text}')"
                )
                if not found:
                    issues.append(f"页面缺少关键元素: '{element_text}'")
                    elements_ok = False

            # 记录结果
            all_passed = all([http_ok, title_ok, console_ok, js_ok, request_ok, resource_ok, not_blank, elements_ok])
            status = "PASS" if all_passed else "FAIL"

            results.append({
                "name": page_name,
                "url": page_url,
                "status": status,
                "load_ms": round(load_ms, 2),
                "render_ms": round(render_ms, 2),
                "total_ms": round(load_ms + render_ms, 2),
                "issues": issues,
                "checks": {
                    "http_status": response.status,
                    "title": title,
                    "console_errors": len(error_collector["console_errors"]),
                    "js_errors": len(error_collector["page_errors"]),
                    "failed_requests": len(error_collector["failed_requests"]),
                    "resource_errors": len(error_collector["resource_errors"]),
                    "body_text_length": len(body_text),
                    "elements_found": elements_ok,
                },
            })

            if issues:
                all_issues[page_name] = issues

        # 打印汇总
        passed = sum(1 for r in results if r["status"] == "PASS")
        failed = len(results) - passed
        print(f"\n{'=' * 70}")
        print(f"页面巡检汇总: {passed}/{len(results)} 通过, {failed} 失败")
        print(f"{'=' * 70}")
        print(f"{'页面':<12} {'状态':<6} {'网络加载':>10} {'渲染稳定':>10} {'总耗时':>10}")
        print(f"{'-' * 70}")
        for r in results:
            icon = "PASS" if r["status"] == "PASS" else "FAIL"
            total = r["load_ms"] + r["render_ms"]
            print(f"  {r['name']:<10} {icon:<6} {r['load_ms']:>8.0f}ms {r['render_ms']:>8.0f}ms {total:>8.0f}ms")
            if r.get("issues"):
                for issue in r["issues"]:
                    print(f"      - {issue}")
        print(f"{'=' * 70}")

        # 生成 JSON 报告
        report_data = {
            "report_time": datetime.now().isoformat(),
            "total_pages": len(results),
            "passed": passed,
            "failed": failed,
            "pages": results,
        }

        report_path = os.path.join(REPORTS_DIR, "page_inspection_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        print(f"\n巡检报告已保存: {report_path}")
        print(f"通过: {passed}/{len(results)}")
        print(f"报告目录: {REPORTS_DIR}")

        # 断言
        assert len(all_issues) == 0, (
            f"{len(all_issues)} 个页面存在问题:\n"
            + "\n".join(
                f"  [{name}] {len(issues)} 个问题:\n"
                + "\n".join(f"    - {issue}" for issue in issues)
                for name, issues in all_issues.items()
            )
        )
