// 平台 -> logo 文件映射（site/public/logos/）
// logo 来源：DuckDuckGo favicon 服务（各平台官方域名），用途为合理引用的平台标识
export const PLATFORM_LOGO: Record<string, string> = {
  '火山方舟': '/logos/volcengine.png',
  '阿里百炼': '/logos/aliyun-bailian.ico',
  '百度千帆': '/logos/baidu-qianfan.ico',
  '腾讯混元/TokenHub': '/logos/tencent-hunyuan.ico',
  '硅基流动': '/logos/siliconflow.png',
  '智谱AI': '/logos/zhipu.png',
  'Kimi': '/logos/moonshot.png',
  'MiniMax': '/logos/minimax.png',
  'DeepSeek': '/logos/deepseek.png',
  'OpenAI': '/logos/openai.png',
  'Anthropic': '/logos/anthropic.png',
  'Google Gemini API': '/logos/google.png',
  'Google Vertex AI': '/logos/google.png',
  'Mistral AI': '/logos/mistral.ico',
  'Cohere': '/logos/cohere.png',
  'xAI': '/logos/xai.ico',
  '讯飞星辰MaaS': '/logos/xfyun.png',
  'HuggingFace': '/logos/huggingface.ico',
  'Artificial Analysis': '/logos/artificial-analysis.ico',
  'LMArena': '/logos/lmarena.ico',
};

export function logoFor(platform: string): string | undefined {
  return PLATFORM_LOGO[platform];
}
