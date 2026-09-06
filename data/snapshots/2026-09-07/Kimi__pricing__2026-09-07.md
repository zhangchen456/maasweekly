<!-- url: see sources config -->
<!-- fetched: 2026-09-07T06:42:36.403647 -->

模型推理价格说明 - Kimi API 开放平台
Documentation Index
Fetch the complete documentation index at: /docs/llms.txt
Use this file to discover all available pages before exploring further.
Skip to main content
🎉 Kimi K3 旗舰模型已正式发布，快来体验吧！
Kimi API 开放平台 home page
简体中文
Search...⌘K
搜索...
Navigation
模型推理定价
模型推理价格说明
模型推理
推理 API 参考
托管智能体 Beta
产品定价
常见问题
资源
模型推理定价
模型推理价格说明
复制页面复制页面
了解 Kimi 模型推理的 token 计费单位、输入输出计费方式、缓存优惠和各模型价格入口。
复制页面复制页面
​
计费基本概念
​
计费单元
Token：代表常见的字符序列，每个汉字使用的 Token 数目可能是不同的。例如，单个汉字”夔”可能会被分解为若干 Token 的组合，而像”中国”这样短且常见的短语则可能会使用单个 Token。大致来说，对于一段通常的中文文本，1 个 Token 大约相当于 1.5-2 个汉字。具体每次调用实际产生的 Tokens 数量可以通过调用计算 Token API 来获得。
​
计费逻辑
Chat Completion 接口收费：我们对 Input 和 Output 均实行按量计费。如果您上传并抽取文档内容，并将抽取的文档内容作为 Input 传输给模型，那么文档内容也将按量计费。文件相关接口（文件内容抽取/文件存储）接口限时免费，即您只上传并抽取文档，这个API本身不会产生费用。
​
模型定价
请查看各模型的详细定价：
Kimi K3
旗舰模型，1M token 上下文
Kimi K2.7 Code
Kimi 的 Coding 模型，多模态模型
Kimi K2.6
支持视觉与文本输入
此页面对您有帮助吗？
是
否