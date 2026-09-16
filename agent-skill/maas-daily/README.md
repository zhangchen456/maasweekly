# MaaS Daily Agent Skill

让 Agent 用自然语言查询 MaaS/大模型平台的最新变化与价格。数据来自 [daily.maas.click](https://daily.maas.click)（观察快照，每个响应带数据版本与截至日期，不代表实时）。

## 支持范围

五类查询：平台变化（含价格事件）、模型价格（原币种/单位/完整条件）、条目详情、证据核验、正式周报。无需注册、无需 API Key。

**不支持**：实时价格、模型推荐、"最低价"判断、写操作。

## 安装

### 方式一：安装脚本（推荐）

```bash
curl -fsSL https://daily.maas.click/maas-skill/install.sh | bash -s -- --dir <目标目录>
```

`--dir` 显式指定 Skill 安装目录（如 `~/.claude/skills` 或 `~/.codex/skills` 下的位置——按你的 Agent 客户端约定）。安装器会下载、校验（文件清单 + SHA-256）后原子替换；**不会**写目标目录之外的任何位置，不使用 sudo。

### 方式二：手动安装

下载 `https://daily.maas.click/maas-skill/` 下全部文件（manifest.json 列出清单）放入 `<skills 目录>/maas-daily/`，核对 manifest 中的 bytes 与 SHA-256。

### 可选：远程 MCP（比 Skill 更结构化）

支持 Streamable HTTP MCP 的客户端可配置：

```json
{ "mcpServers": { "maas-daily": { "type": "http", "url": "https://daily.maas.click/api/mcp" } } }
```

Codex（config.toml）：

```toml
[mcp_servers.maas-daily]
url = "https://daily.maas.click/api/mcp"
```

## 验证安装

**安装成功以完成一次真实查询为准**（不是文件下载成功）。开一个新会话问：

1. 「用 maas-daily 查一下最近几天 OpenAI 有什么变化」——应引用数据版本/截至日期
2. 「gpt-4o 的输入价格是多少？」——应含币种、单位、条件与证据 ID
3. 「最新一期周报讲了什么？」——应是日期型 ID 的正式周报

不通过时参考下方故障恢复。配置 MCP 后可能需要**开新会话**才能发现工具。

## 更新与卸载

- 更新：重跑安装命令（同 `--dir`）。目标是合法 maas-daily 时升级（先备份，失败自动恢复旧版）；目标含其他 Skill 或未知文件时拒绝覆盖。
- 卸载：删除 `maas-daily` 目录即可（无注册表、无残留）。

## 版本兼容

| Skill 包版本 | API | MCP 协议 |
|---|---|---|
| 1.0.0 | v1 | Streamable HTTP（SDK 协商） |

## 故障恢复

- 查询失败/超时 → 如实报告，稍后重试；**不要**用模型记忆回答实时价格
- 「未记录到匹配项」→ 是覆盖范围内无记录，不等于没变化/模型不存在
- cursor 过期（dataset_version_expired）→ 从第一页重查
- 详细错误码：references/errors.md

## 许可

本 Skill 代码与文档采用 MIT 许可（见 LICENSE）。MaaS Daily **数据**的使用边界见站点说明——公共测试期使用边界待补充，MIT 不覆盖数据许可。
