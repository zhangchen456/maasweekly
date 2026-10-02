/** Editorial selection, independent of catalog/quote coverage. Review against official docs. */
export interface HomeModelPick {
  modelId: string;
  name: string;
  providerId: string;
  reason: string;
  reasonEn: string;
  source: string;
  holdQuoteReason?: string;
}
const pick = (providerId: string, key: string, name: string, reason: string, reasonEn: string, source: string, holdQuoteReason?: string): HomeModelPick =>
  ({ modelId: `${providerId}:${key}`, name, providerId, reason, reasonEn, source, holdQuoteReason });
const openai = 'https://developers.openai.com/api/docs/models';
const claude = 'https://platform.claude.com/docs/en/models/overview';
const google = 'https://ai.google.dev/gemini-api/docs/models';
const qwen = 'https://help.aliyun.com/zh/model-studio/models';
const deepseek = 'https://api-docs.deepseek.com/quick_start/pricing/';
const glm = 'https://docs.bigmodel.cn/cn/guide/start/model-overview';
const kimi = 'https://platform.kimi.com/docs/models';
const doubao = 'https://docs.volcengine.com/docs/ark/model-pricing?lang=zh';
export const HOME_MODEL_REVIEWED_AT = '2026-10-02';
export const HOME_MODEL_GROUPS = [
  { id: 'flagship', title: '旗舰能力', titleEn: 'Flagship capability', description: '关注复杂推理、知识工作与长程任务。分组依据官方定位，不代表效果排名。', descriptionEn: 'For complex reasoning, knowledge work and long-running tasks. Vendor positioning, not a benchmark ranking.', models: [
    pick('openai', 'gpt-6-astra', 'GPT-6 Astra', '复杂推理与专业工作', 'Complex reasoning and professional work', openai),
    pick('anthropic', 'claude-opus-5.5', 'Claude Opus 5.5', '长程智能体与知识工作', 'Long-running agents and knowledge work', claude),
    pick('google', 'gemini-3.1-pro-preview', 'Gemini 3.1 Pro Preview', '复杂任务与工具调用 · 预览版', 'Complex tasks and tool use · Preview', google),
    pick('alibaba', 'qwen3.8-max', 'Qwen3.8 Max', '千问 Max 通用能力档', 'Qwen Max general capability tier', qwen),
    pick('deepseek', 'deepseek-v4-pro', 'DeepSeek V4 Pro', 'Pro 通用能力档', 'Pro general capability tier', deepseek, '价格变更待核验'),
    pick('zhipu', 'glm-5.3', 'GLM-5.3', '复杂工程与长程智能体', 'Complex engineering and long-running agents', glm),
    pick('kimi', 'kimi-k3', 'Kimi K3', '深度推理与知识工作', 'Deep reasoning and knowledge work', kimi, '价格变更待核验'),
    pick('volcengine', 'doubao-seed-2.1-pro', 'Doubao Seed 2.1 Pro', 'Seed Pro 通用能力档', 'Seed Pro general capability tier', doubao),
  ] },
  { id: 'value', title: '主力性价比', titleEn: 'Everyday value', description: '关注日常任务的能力、成本与响应速度；性价比取决于你的实际任务。', descriptionEn: 'Balance capability, cost and speed for everyday work. Value depends on your workload.', models: [
    pick('openai', 'gpt-6.1-sol', 'GPT-6.1 Sol', '平衡能力、速度与成本', 'Balance intelligence, speed and cost', openai),
    pick('anthropic', 'claude-sonnet-5.5', 'Claude Sonnet 5.5', '速度与能力的均衡档', 'Balance speed and intelligence', claude),
    pick('google', 'gemini-3.8-flash', 'Gemini 3.8 Flash', '当前 Flash 主力型号', 'Current mainstream Flash model', google),
    pick('alibaba', 'qwen3.7-plus', 'Qwen3.7 Plus', '千问 Plus 通用主力档', 'Qwen Plus everyday tier', qwen),
    pick('deepseek', 'deepseek-flash', 'DeepSeek V4.1 Flash', '当前 Flash 调用名：deepseek-flash', 'Current Flash API name: deepseek-flash', deepseek),
    pick('zhipu', 'glm-5.3-flash', 'GLM-5.3 Flash', '普惠的通用多模态档', 'Accessible general multimodal tier', glm),
    pick('kimi', 'kimi-k2.6', 'Kimi K2.6', '仍可用的通用型号 · 上一代', 'Available general-purpose model · Previous generation', kimi),
    pick('volcengine', 'doubao-seed-2.1-turbo', 'Doubao Seed 2.1 Turbo', 'Seed Turbo 主力档', 'Seed Turbo everyday tier', doubao),
  ] },
  { id: 'coding', title: '编程专项', titleEn: 'Coding specialists', description: '专用编程模型单独比较，避免与通用模型混为同一档。', descriptionEn: 'Compare dedicated coding models separately from general-purpose tiers.', models: [
    pick('alibaba', 'qwen3-coder-plus', 'Qwen3 Coder Plus', '代码生成与编程智能体', 'Code generation and coding agents', 'https://help.aliyun.com/zh/model-studio/models'),
    pick('kimi', 'kimi-k2.7-code', 'Kimi K2.7 Code', '长上下文编程任务', 'Long-context coding tasks', kimi),
  ] },
] as const;
