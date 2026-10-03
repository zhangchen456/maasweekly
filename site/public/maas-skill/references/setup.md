# Skill 可用性前置检查与配置

Skill 安装后，必须确认数据入口可用。Skill 有两种数据入口：MCP 工具（`maas_get_*` 五个）或 REST API。两者都不可用 = Skill 无法工作。

## 一、MCP 工具可用性

Skill 的 MCP 入口是 `POST https://daily.maas.click/api/mcp`。MCP 工具是否可用取决于用户环境是否配置了 MaaS Daily MCP server。

### 如何配置 MCP server（Claude Code）

在 Claude Code 配置文件（`~/.claude.json` 或项目 `.mcp.json`）中添加：

```json
{
  "mcpServers": {
    "maas-daily": {
      "type": "http",
      "url": "https://daily.maas.click/api/mcp"
    }
  }
}
```

配置后重启 Claude Code，Skill 可直接使用 `maas_get_changes`/`maas_get_prices`/`maas_get_item`/`maas_get_evidence`/`maas_get_weekly` 五个工具。

### 如何确认 MCP 可用

新会话中执行任意查询（如"用 maas-daily 查最近变化"）。如果 MCP 工具可用，Skill 会调用 `maas_get_changes`；如果报"没有可用的 maas_get_changes 工具"，则 MCP 未配置或不可用。

## 二、REST API 可用性

Skill 在 MCP 不可用时会 fallback 到 REST（`https://daily.maas.click/api/v1/*`，匿名无需 Key）。REST 可用性取决于执行环境的网络访问。

### 网络访问检查

REST API 在公网（`https://daily.maas.click`）上运行，任何 HTTP 客户端均可访问。如果 Skill 报"网页查询也无法访问其 API"，可能是：

1. 执行环境无网络访问（离线 / 代理未配置）
2. 网络 DNS 解析失败
3. 临时网络故障

### 代理配置（如需要）

如果执行环境需要代理（如中国大陆网络），设置环境变量后重试：

```bash
export https_proxy=http://127.0.0.1:7897
export http_proxy=http://127.0.0.1:7897
```

### 手动 REST 验证

```bash
curl -sf "https://daily.maas.click/api/v1/status"
```

返回 JSON 含 `datasetVersion` 和 `dataThrough` 即表示 API 可用。

## 三、两者都不可用时的恢复

如果 MCP 工具和 REST 都不可用：

1. **不要用模型训练数据补答**实时价格/变化——训练数据有截止日期，价格早已变化
2. 告知用户："MaaS Daily 数据入口不可用，可能原因：MCP 未配置 / 网络不可达。请在 Claude Code 配置 MaaS server（见 references/setup.md），或确认网络代理后重试。"
3. 如需手动查询，引导用户在浏览器或终端执行 REST 请求（见上"手动 REST 验证"）

## 四、安装后自检流程

Skill 安装完成后，建议在新会话中执行自检：

1. 问"用 maas-daily 查一下最近几天有什么变化"
2. 如果返回数据 → Skill 可用
3. 如果报"没有可用的 maas_get_changes 工具" → MCP 未配置，按上面"如何配置 MCP server"配置
4. 如果报"网页查询也无法访问" → 网络问题，按"代理配置"处理

## 四、专业情报接入（开发完成，生产待发布）

现有匿名查询保持不变。专业情报需单独配置服务端和网站生成的通用凭证；不要向用户索要模型厂商API Key，不把凭证粘贴进对话、提示词或Skill正文。生产发布后才启用下列入口，404/503时说明暂不可用，不用模型知识补出专业全文。

专业MCP端点：`https://daily.maas.click/api/pro/mcp`。客户端使用其安全配置/环境变量功能设置`Authorization: Bearer <MAAS_PRO_TOKEN>`请求头；环境变量插值语法按各客户端文档配置，不能假定`${...}`在所有客户端通用。

工具：`maas_pro_catalog`返回预览，`maas_pro_read`读取指定内容，`maas_pro_reports`读取自己的报告索引或指定报告。响应含版本、条件与来源；遇到更正/撤回需明确说明。

REST入口：`/api/pro/catalog`、`/api/pro/content/{id}`、`/api/pro/me`、`/api/pro/report/{id}`。授权头由客户端注入，不出现在URL。网站管理页是`/pro/`。

401：检查凭证是否到期/撤销，回网站重新生成；403：检查当前服务权益及凭证用途；404：核对内容ID或撤回状态，不能改用他人的报告ID；503：稍后重试。RSS私有地址只有RSS用途，不能替代通用Token。专业权限错误不影响匿名免费查询。
