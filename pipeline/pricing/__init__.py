"""价格模块：8 家厂商官方定价页的结构化抓取与解析。

迁移自追浪 app-core-service-001 的 goals/ 模块（2026-09）。
模块组成：registry（信源）→ providers（playwright 渲染）→ extractors（解析）
→ normalize（门禁）→ factdiff（版本 diff）→ view_data（展示归一）。
入口脚本：pipeline/scripts/fetch-prices.py
"""
