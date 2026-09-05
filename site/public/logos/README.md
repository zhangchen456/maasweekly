# 平台 Logo 资源库

当前官方资源位于 `official/`，以稳定平台 ID + 内容哈希命名。旧文件保留供历史引用，新页面统一通过 `src/lib/platforms.ts` 的 `logoFor(name)` 查找。

## 数据与匹配

唯一配置：`site/src/data/platform-logos.json`，记录平台 ID、标准名、别名、官方来源页面、下载地址、本地路径、SHA-256、核验时间。当前覆盖抓取配置中的 17 个平台和 3 个行业信源。

匹配支持大小写、空格与常见标点归一化，以及明确登记的别名。不做模糊猜测；未知平台返回 undefined，由页面展示文字占位。Gemini 与 Vertex AI 分别映射，不合并为 Google。

图标是核验时官方站点实际提供的产品 / 品牌标识；部分站点仅提供母品牌 favicon（如百度千帆、Vertex AI）。核验日期表示抓取时间，不代表品牌发布日期。小尺寸图标使用 SVG 或官方 favicon，不拉伸为横版字标，不重绘品牌图形。

## 刷新

在仓库根目录运行：

```bash
python3 site/scripts/refresh-logos.py
python3 site/scripts/refresh-logos.py --platform Kimi
```

脚本下载公开资源、检查图片格式和 SVG 外部引用、生成内容哈希文件名并更新映射与 `/logos/index.html` 预览。下载失败保留上一次成功资源并返回非零退出码。官方路径变化时，先查看官方页面更新 candidates，再运行刷新。

每日内容更新无需下载图标：构建时按平台名称查询本地映射即可。新增平台时，先添加稳定 ID、别名及官方资源地址，再刷新。资源作为平台识别标志使用，商标归各品牌所有。
