"""E2E 测试 HTML 报告生成器

从 JSON 报告生成可视化的 HTML 报告，包含：
- 页面状态概览（通过/失败）
- 加载耗时柱状图
- 错误详情列表
- 响应式布局，支持移动端查看

使用方式：
    python tests/e2e/generate_html_report.py
    # 或指定报告路径
    python tests/e2e/generate_html_report.py --error-report tests/e2e/reports/page_error_monitor_report.json
    python tests/e2e/generate_html_report.py --inspection-report tests/e2e/reports/page_inspection_report.json
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# Set UTF-8 encoding for Windows CI
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


REPORTS_DIR = Path(__file__).parent / "reports"


def load_json_report(report_path: str) -> dict:
    """加载 JSON 报告"""
    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_html_report(error_report: dict, inspection_report: dict, output_path: str):
    """生成 HTML 报告"""
    
    # 统计信息
    error_total = error_report.get("total_pages", 0)
    error_clean = error_report.get("all_clean", False)
    error_pass = sum(1 for p in error_report.get("pages", {}).values() if p.get("status") == "PASS") if isinstance(error_report.get("pages"), dict) else sum(1 for p in error_report.get("pages", []) if p.get("status") == "PASS")
    error_fail = error_total - error_pass
    
    inspection_total = inspection_report.get("total_pages", 0)
    inspection_pass = inspection_report.get("passed", 0)
    inspection_fail = inspection_report.get("failed", 0)
    
    # 生成页面表格行
    def generate_page_rows(report_data: dict, report_type: str) -> str:
        rows = []
        pages = report_data.get("pages", {})
        
        # 处理 dict 格式（错误监控报告）
        if isinstance(pages, dict):
            page_items = pages.items()
        # 处理 list 格式（页面巡检报告）
        elif isinstance(pages, list):
            page_items = [(p.get("name", ""), p) for p in pages]
        else:
            page_items = []
        
        for page_name, page_data in page_items:
            status = page_data.get("status", "UNKNOWN")
            status_class = "pass" if status == "PASS" else "fail"
            status_icon = "✓" if status == "PASS" else ""
            
            load_ms = page_data.get("load_ms", 0)
            render_ms = page_data.get("render_ms", 0)
            total_ms = page_data.get("total_ms", load_ms + render_ms)
            
            error_count = page_data.get("error_count", page_data.get("checks", {}).get("console_errors", 0) + page_data.get("checks", {}).get("js_errors", 0))
            issues = page_data.get("issues", [])
            
            # 构建问题列表 HTML
            issues_html = ""
            if issues:
                issues_html = '<div class="issues-list">'
                for issue in issues:
                    issues_html += f'<div class="issue-item"> {issue}</div>'
                issues_html += '</div>'
            
            rows.append(f"""
            <tr class="{status_class}">
                <td>{page_name}</td>
                <td><span class="status-badge {status_class}">{status_icon} {status}</span></td>
                <td>{load_ms:.0f}ms</td>
                <td>{render_ms:.0f}ms</td>
                <td>{total_ms:.0f}ms</td>
                <td>{error_count}</td>
                <td>{issues_html if issues_html else '-'}</td>
            </tr>
            """)
        
        return "\n".join(rows)
    
    # 生成耗时图表数据（JSON 格式，用于 Chart.js）
    def generate_chart_data(report_data: dict) -> dict:
        labels = []
        load_times = []
        render_times = []
        
        pages = report_data.get("pages", {})
        
        # 处理 dict 格式（错误监控报告）
        if isinstance(pages, dict):
            for page_name, page_data in pages.items():
                labels.append(page_name)
                load_times.append(page_data.get("load_ms", 0))
                render_times.append(page_data.get("render_ms", 0))
        # 处理 list 格式（页面巡检报告）
        elif isinstance(pages, list):
            for page_data in pages:
                labels.append(page_data.get("name", ""))
                load_times.append(page_data.get("load_ms", 0))
                render_times.append(page_data.get("render_ms", 0))
        
        return {
            "labels": labels,
            "load_times": load_times,
            "render_times": render_times
        }
    
    error_chart_data = generate_chart_data(error_report)
    inspection_chart_data = generate_chart_data(inspection_report)
    
    # HTML 模板
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E2E 测试报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        
        header .subtitle {{
            opacity: 0.9;
            font-size: 14px;
        }}
        
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .card h3 {{
            font-size: 14px;
            color: #666;
            margin-bottom: 10px;
        }}
        
        .card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #333;
        }}
        
        .card .value.pass {{
            color: #10b981;
        }}
        
        .card .value.fail {{
            color: #ef4444;
        }}
        
        .section {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .section h2 {{
            font-size: 20px;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        th {{
            background: #f9fafb;
            font-weight: 600;
            color: #374151;
        }}
        
        tr.pass {{
            background: #f0fdf4;
        }}
        
        tr.fail {{
            background: #fef2f2;
        }}
        
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }}
        
        .status-badge.pass {{
            background: #10b981;
            color: white;
        }}
        
        .status-badge.fail {{
            background: #ef4444;
            color: white;
        }}
        
        .issues-list {{
            margin-top: 5px;
        }}
        
        .issue-item {{
            background: #fef3c7;
            padding: 8px 12px;
            border-radius: 6px;
            margin-bottom: 5px;
            font-size: 13px;
            color: #92400e;
        }}
        
        .chart-container {{
            position: relative;
            height: 400px;
            margin-top: 20px;
        }}
        
        footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 14px;
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}
            
            header {{
                padding: 20px;
            }}
            
            header h1 {{
                font-size: 22px;
            }}
            
            table {{
                font-size: 12px;
            }}
            
            th, td {{
                padding: 8px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🧪 E2E 页面监控测试报告</h1>
            <div class="subtitle">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </header>
        
        <!-- 概览卡片 -->
        <div class="summary-cards">
            <div class="card">
                <h3>错误监控 - 总页面数</h3>
                <div class="value">{error_total}</div>
            </div>
            <div class="card">
                <h3>错误监控 - 通过</h3>
                <div class="value pass">{error_pass}</div>
            </div>
            <div class="card">
                <h3>错误监控 - 失败</h3>
                <div class="value fail">{error_fail}</div>
            </div>
            <div class="card">
                <h3>页面巡检 - 总页面数</h3>
                <div class="value">{inspection_total}</div>
            </div>
            <div class="card">
                <h3>页面巡检 - 通过</h3>
                <div class="value pass">{inspection_pass}</div>
            </div>
            <div class="card">
                <h3>页面巡检 - 失败</h3>
                <div class="value fail">{inspection_fail}</div>
            </div>
        </div>
        
        <!-- 错误监控详情 -->
        <div class="section">
            <h2>📊 错误监控详情</h2>
            <table>
                <thead>
                    <tr>
                        <th>页面</th>
                        <th>状态</th>
                        <th>网络加载</th>
                        <th>渲染稳定</th>
                        <th>总耗时</th>
                        <th>问题数</th>
                        <th>问题详情</th>
                    </tr>
                </thead>
                <tbody>
                    {generate_page_rows(error_report, "error")}
                </tbody>
            </table>
        </div>
        
        <!-- 页面巡检详情 -->
        <div class="section">
            <h2> 页面巡检详情</h2>
            <table>
                <thead>
                    <tr>
                        <th>页面</th>
                        <th>状态</th>
                        <th>网络加载</th>
                        <th>渲染稳定</th>
                        <th>总耗时</th>
                        <th>问题数</th>
                        <th>问题详情</th>
                    </tr>
                </thead>
                <tbody>
                    {generate_page_rows(inspection_report, "inspection")}
                </tbody>
            </table>
        </div>
        
        <!-- 耗时图表 -->
        <div class="section">
            <h2>⏱️ 页面加载耗时对比</h2>
            <div class="chart-container">
                <canvas id="loadTimeChart"></canvas>
            </div>
        </div>
        
        <footer>
            <p>E2E 页面监控测试报告 | 自动生成</p>
        </footer>
    </div>
    
    <script>
        // 图表数据
        const chartData = {{
            labels: {json.dumps(error_chart_data['labels'], ensure_ascii=False)},
            loadTimes: {json.dumps(error_chart_data['load_times'])},
            renderTimes: {json.dumps(error_chart_data['render_times'])}
        }};
        
        // 创建图表
        const ctx = document.getElementById('loadTimeChart').getContext('2d');
        new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: chartData.labels,
                datasets: [
                    {{
                        label: '网络加载 (ms)',
                        data: chartData.loadTimes,
                        backgroundColor: 'rgba(102, 126, 234, 0.8)',
                        borderColor: 'rgba(102, 126, 234, 1)',
                        borderWidth: 1
                    }},
                    {{
                        label: '渲染稳定 (ms)',
                        data: chartData.renderTimes,
                        backgroundColor: 'rgba(118, 75, 162, 0.8)',
                        borderColor: 'rgba(118, 75, 162, 1)',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{
                            display: true,
                            text: '耗时 (ms)'
                        }}
                    }},
                    x: {{
                        title: {{
                            display: true,
                            text: '页面'
                        }},
                        ticks: {{
                            maxRotation: 45,
                            minRotation: 45
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: true,
                        position: 'top'
                    }},
                    title: {{
                        display: true,
                        text: '页面加载耗时分析',
                        font: {{
                            size: 16
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    
    # 写入 HTML 文件
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✓ HTML 报告已生成：{output_path}")


def main():
    parser = argparse.ArgumentParser(description="生成 E2E 测试 HTML 报告")
    parser.add_argument("--error-report", default=str(REPORTS_DIR / "page_error_monitor_report.json"),
                        help="错误监控报告路径")
    parser.add_argument("--inspection-report", default=str(REPORTS_DIR / "page_inspection_report.json"),
                        help="页面巡检报告路径")
    parser.add_argument("--output", default=str(REPORTS_DIR / "e2e_test_report.html"),
                        help="输出 HTML 报告路径")
    
    args = parser.parse_args()
    
    # 加载报告
    print("加载 JSON 报告...")
    error_report = load_json_report(args.error_report)
    inspection_report = load_json_report(args.inspection_report)
    
    # 生成 HTML 报告
    print("生成 HTML 报告...")
    generate_html_report(error_report, inspection_report, args.output)
    
    print("完成！")


if __name__ == "__main__":
    main()
