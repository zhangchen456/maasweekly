<!-- url: see sources config -->
<!-- fetched: 2026-09-06T06:39:15.095163 -->

更新公告
搜索
⌘K
使用指南
场景示例
API手册
文本系列
创建对话请求(OpenAI) POST
创建对话请求(Anthropic) POST
创建嵌入请求 POST
创建重排序请求 POST
图像系列
创建图片生成请求 POST
语音系列
上传参考音频 POST
创建文本转语音请求 POST
获取参考音频列表 GET
删除参考音频 POST
创建语音转文本请求 POST
视频系列
创建视频生成请求 POST
获取视频生成链接请求 POST
批量处理
获取文件列表 GET
上传文件 POST
获取batch任务列表 GET
创建batch任务 POST
获取batch任务详情 GET
取消batch任务 POST
平台系列
获取用户模型列表 GET
条款与协议
更新公告
更多
SiliconFlow 平台
SiliconFlow 官网
预留实例
企业级 MaaS 平台（私有化）
私有化大模型服务网关
AI 算力运营服务
中文
更新公告
更新公告
SiliconFlow 平台更新日志，涵盖模型上下线、服务调整、价格变更及新功能发布等关键公告。
2026.09.03
【模型服务调整】Nex-N2-Pro、Qwen3.5-397B-A17B、MiniMax-M2.5 等模型将下线
为进一步优化资源配置，提供更先进、优质的技术服务，平台将于 2026-09-11 对下列模型进行下线处理：
nex-agi/Nex-N2-Pro
Qwen/Qwen3.5-397B-A17B
MiniMaxAI/MiniMax-M2.5
Pro/MiniMaxAI/MiniMax-M2.5
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2026.08.25
【模型价格调整】DeepSeek-V4-Flash 模型分时段定价调整
deepseek-ai/DeepSeek-V4-Flash 模型将于 2026-09-01 起实行分时段定价，不同时段执行不同价格。
|
| 费用发生时段 | 缓存命中 | 未命中（输入） | 输出
| 每日 2:00 ～ 8:00（北京时间） | ¥0.15 / M Tokens | ¥1.5 / M Tokens | ¥4.5 / M Tokens
| 其他时间 | ¥0.3 / M Tokens | ¥3 / M Tokens | ¥9 / M Tokens
若您正在使用上述模型，请关注费用账单。
注：价格可能发生调整，请以平台实时展示价格信息为准。
2026.08.11
【接口服务调整】/user/info 接口将停止服务
由于系统更新迭代，/user/info 接口已无法适配平台用户账户体系，该 API 将于 2026-08-14（周五） 正式停止服务，届时接口将不再可用。
后续，平台将适时提供账户层面的替代 API，以便您更便捷地获取所需的账户信息。新接口上线后将在本页面另行通知。
若您仍在使用 /user/info 接口，请尽快移除相关调用，感谢您的理解与配合。
2026.07.29
【模型价格调整】DeepSeek-V4-Pro 缓存命中输入 tokens 价格调整
deepseek-ai/DeepSeek-V4-Pro 模型将于 2026-08-03 起调整缓存命中输入 tokens 价格，调整后价格如下：
缓存命中：¥1 / M Tokens
若您正在使用上述模型，请关注费用账单。
注：价格可能发生调整，请以平台实时展示价格信息为准。
2026.06.25
【模型价格调整】Nex-N2-Pro、DeepSeek-V4-Pro、DeepSeek-V3.2、Qwen3.6 模型价格调整
nex-agi/Nex-N2-Pro 模型免费体验活动即将结束，平台将于 2026-06-26 起正式开始收费**，价格信息如下：
输入：¥1.75 / M Tokens
输出：¥7 / M Tokens
缓存命中：¥0.175 / M Tokens
deepseek-ai/DeepSeek-V4-Pro 模型限时折扣将于 2026-06-30 结束，将恢复原价计费**：
输入：¥12 / M Tokens
输出：¥24 / M Tokens
缓存命中：¥0.1 / M Tokens
Pro/deepseek-ai/DeepSeek-V3.2 及 deepseek-ai/DeepSeek-V3.2 价格将于 2026-06-30 进行调整：
输入：¥4 / M Tokens
输出：¥6 / M Tokens
缓存命中：¥0.4 / M Tokens
Qwen/Qwen3.6-27B 模型价格将于 2026-06-30 进行调整，不再区分输入长度区间：
输入：¥3 / M Tokens
输出：¥18 / M Tokens
Qwen/Qwen3.6-35B-A3B 模型价格将于 2026-06-30 进行调整，不再区分输入长度区间：
输入：¥1.8 / M Tokens
输出：¥10.8 / M Tokens
若您正在使用上述任一模型，请关注费用账单。
注：价格可能发生调整，请以平台实时展示价格信息为准。
2026.06.05
【模型服务调整】GLM-4.7、Kimi-K2.5 等模型将下线
为进一步优化资源配置，提供更先进、优质的技术服务，平台将于 2026-06-11 对下列模型进行下线处理：
Pro/moonshotai/Kimi-K2.5（请求将指向 K2.6）
Pro/zai-org/GLM-5（请求将指向 GLM-5.1）
Pro/zai-org/GLM-4.7
netease-youdao/bce-embedding-base_v1
netease-youdao/bce-reranker-base_v1
其中，Pro/moonshotai/Kimi-K2.5 和 Pro/zai-org/GLM-5 下线后，请求将分别被指向 Pro/moonshotai/Kimi-K2.6 和 Pro/zai-org/GLM-5.1，并按照相应的模型计量计费。
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2026.05.08
【模型服务调整】Kimi-K2、GLM-4.6 等多款模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2026-05-15 对下列模型进行下线处理：
moonshotai/Kimi-K2-Thinking
moonshotai/Kimi-K2-Instruct-0905
Pro/moonshotai/Kimi-K2-Instruct-0905
Pro/moonshotai/Kimi-K2-Thinking
zai-org/GLM-4.6
zai-org/GLM-4.6V
THUDM/GLM-Z1-32B-0414
THUDM/GLM-4.1V-9B-Thinking
inclusionAI/Ring-flash-2.0
Qwen/Qwen3-30B-A3B-Thinking-2507
Qwen/Qwen3-235B-A22B-Instruct-2507
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2026.05.07
【账户安全】未完成实名认证账户将限制使用平台功能
为进一步保障您的账户安全与平台权益，提升服务安全性与可靠性，自 2026 年 5 月 15 日起，未完成实名认证的账户将无法使用平台功能，需完成认证后解除限制
2026.04.22
【模型服务调整】KAT-Dev、PaddleOCR-VL 等多款模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2026-04-29 对下列模型进行下线处理：
Kwaipilot/KAT-Dev
PaddlePaddle/PaddleOCR-VL
Qwen/QwQ-32B
Qwen/Qwen2.5-VL-32B-Instruct
Qwen/Qwen2.5-VL-72B-Instruct
deepseek-ai/DeepSeek-R1-Distill-Qwen-32B
deepseek-ai/DeepSeek-R1-Distill-Qwen-14B
deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
Qwen/Qwen2.5-Coder-32B-Instruct
Qwen/Qwen2-VL-72B-Instruct
internlm/internlm2_5-7b-chat
IndexTeam/IndexTTS-2
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2026.04.15
【模型服务调整】Qwen3-Coder、ERNIE-4.5 等多款模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2026-04-22 对下列模型进行下线处理：
Qwen/Qwen3-Coder-480B-A35B-Instruct
Qwen/Qwen3-235B-A22B-Thinking-2507
Qwen/Qwen3-VL-235B-A22B-Thinking
Qwen/Qwen3-VL-235B-A22B-Instruct
deepseek-ai/DeepSeek-V2.5
baidu/ERNIE-4.5-300B-A47B
ascend-tribe/pangu-pro-moe
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2026.03.10
【模型服务调整】MiniMax-M2.1、Qwen2 等多款模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2026-03-17 对下列模型进行下线处理：
Pro/MiniMaxAI/MiniMax-M2.1
Pro/Qwen/Qwen2-7B-Instruct
Qwen/Qwen2-7B-Instruct
Pro/THUDM/glm-4-9b-chat
THUDM/glm-4-9b-chat
deepseek-ai/deepseek-vl2
Pro/Qwen/Qwen2.5-VL-7B-Instruct
Qwen/Qwen3-Next-80B-A3B-Thinking
Qwen/Qwen3-Next-80B-A3B-Instruct
Qwen/Qwen2.5-Coder-7B-Instruct
Pro/Qwen/Qwen2.5-Coder-7B-Instruct
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2026.03.09
【价格调整】Qwen3.5-397B-A17B 模型定价调整
为了确保平台模型定价体系的合理性与一致性，平台对 Qwen/Qwen3.5-397B-A17B 模型的价格进行了调整。详情请前往「模型广场」查看详情。
感谢您的支持与理解！
2026.02.02
【模型服务调整】MiniMax-M2、Kimi-Dev-72B 等多款模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2026-02-09 对下列模型进行下线处理：
MiniMaxAI/MiniMax-M2
MiniMaxAI/MiniMax-M1-80k
moonshotai/Kimi-Dev-72B
Pro/THUDM/GLM-4.1V-9B-Thinking
Tongyi-Zhiwen/QwenLong-L1-32B
Qwen/QVQ-72B-Preview
THUDM/GLM-Z1-Rumination-32B-0414
Pro/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
Qwen/Qwen3-30B-A3B
stepfun-ai/step3
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2025.12.24
【模型服务调整】GLM-4.5、Qwen3-235B 等模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2025-12-31 对下列模型进行下线处理：
zai-org/GLM-4.5
Qwen/Qwen3-235B-A22B
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2025.12.17
【服务调整】平台赠送余额展示形式调整
为更好地保障您的平台权益、提升资源使用效率，平台对赠送余额服务展示形式进行如下调整：
2025 年 11 月 30 日前已使用的赠送余额，统一转化为一张已用尽代金券：
该代金券总金额、已使用金额均为您历史累计已消耗的赠送余额；
该代金券当前剩余可用金额为 0，仅用于记录历史权益，对后续业务不产生影响。
2025 年 11 月 30 日前已获得，但尚未使用的赠送余额，转化为一张可用代金券：
该代金券总额与 11 月 30 日剩余赠送余额一致；
目前，该代金券可用范围与此前的赠送余额可用范围保持一致，可正常抵扣使用，如后续可用范围调整以代金券描述范围为准；
该代金券有效期至 2099-12-31 23:59:59
2025 年 11 月 30 日后，平台激励以代金券形式发放。。
您可前往 【余额充值 > 代金券】 点击代金券数量，查看代金券列表及代金券详情。
2025.12.04
【模型升级】DeepSeek-V3.2-Exp 升级至 V3.2
为进一步优化模型服务质量，平台将于今明两日逐步更新Deepseek-V3.2-Exp模型为Deepseek-V3.2版本。您对Pro/deepseek-ai/DeepSeek-V3.2-Exp、deepseek-ai/DeepSeek-V3.2-Exp的请求将分别指向Pro/deepseek-ai/DeepSeek-V3.2、deepseek-ai/DeepSeek-V3.2。
2025.11.17
【模型服务调整】Ling-1T、Ring-1T 等模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2025-11-20 对下列模型进行下线处理：
inclusionAI/Ling-1T
inclusionAI/Ring-1T
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2025.11.11
【服务调整】DeepSeek-R1/V3 等模型速率限制调整
为进一步优化资源配置，提供更高效、稳定的算力服务，平台将于2025 年 11 月 11 日起对部分模型 Rate Limits 进行调整。
此次调整的模型是：Pro/deepseek-ai/DeepSeek-R1，Pro/deepseek-ai/DeepSeek-V3，Pro/deepseek-ai/DeepSeek-V3.1-Terminus，zai-org/GLM-4.6，inclusionAI/Ling-1T，inclusionAI/Ring-1T，MiniMaxAI/MiniMax-M2；
如您业务对高并发或大规模吞吐有特殊需求，可联系我们申请更高额度。
感谢您的理解与支持。
2025.11.06
【服务调整】关闭使用等级购买入口
为进一步优化资源配置，提供更高效、稳定的算力服务，平台将于 2025 年 11 月 7 日 起关闭等级包的售卖入口。
此次调整仅影响新购入口的开放，您已购的等级包、当前的用量等级及平台根据消费金额自动升降的机制不受影响。
如您有快速提升用量等级、提高 Rate Limits 的需求，请联系我们。
感谢您的理解与支持。
2025.09.29
【模型服务调整】DeepSeek-V3.1 模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2025-10-09 对下列模型进行下线处理：
deepseek-ai/DeepSeek-V3.1
Pro/deepseek-ai/DeepSeek-V3.1
若您正在使用上述任一模型，建议您尽快切换到 V3.1 Terminus，以免服务受到影响。
2025.09.16
【模型更新】Kimi-K2-Instruct 升级至 0905 版本
为进一步优化模型服务质量，平台已于 09 月 15 更新 moonshotai/Kimi-K2-Instruct 和 Pro/moonshotai/Kimi-K2-Instruct 模型至最新的 0905 版本，此前的 0711 版本不再继续提供。
模型广场中moonshotai/Kimi-K2-Instruct 和 Pro/moonshotai/Kimi-K2-Instruct 已经下线，所有对应模型请求将被分别指向 moonshotai/Kimi-K2-Instruct-0905 和 Pro/moonshotai/Kimi-K2-Instruct-0905。
2025.08.22
【模型服务调整】HunyuanVideo-HD 等视频模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2025 年 9 月 4 日 对下列模型进行下线处理：
tencent/HunyuanVideo-HD
Wan-AI/Wan2.1-I2V-14B-720P-Turbo
Wan-AI/Wan2.1-I2V-14B-720P
Wan-AI/Wan2.1-T2V-14B-Turbo
Wan-AI/Wan2.1-T2V-14B
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2025.06.23
【模型服务调整】DeepSeek-R1-0120 等模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2025 年 7 月 3 日 对下列模型进行下线处理：
Pro/deepseek-ai/DeepSeek-R1-0120
Pro/deepseek-ai/DeepSeek-V3-1226
Qwen/QwQ-32B-Preview
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2025.06.06
【平台维护】6 月 10 日平台维护通知
为提供更加丰富、先进、优质的服务，平台将于 2025 年 6 月 10 日 23 时至 11 日 8 时进行维护。
受系统维护影响：
cloud.siliconflow.cn 将暂停注册、登录以及包括不限于下列功能的界面操作：
模型在线体验/微调/批量推理；
官网模型广场查看模型列表及详细信息；
在线充值、购买等级包、查询账单、开具发票等；
/user/info API 调整，name / image / email 字段将不再返回，固定输出空字符串；
平台 API 服务不受维护影响，可以持续调用，建议您提前关注账户余额，以免因为余额不足导致服务受限。
2025.05.29
【模型更新】DeepSeek-R1 升级至 0528 版本
SiliconFlow 将启动 DeepSeek R1 模型更新。
对于 deepseek-ai/DeepSeek-R1 和 Pro/deepseek-ai/DeepSeek-R1 模型，将“逐步“更新到最新 0528 版本。
更新完成后，上述两个款模型均为 0528 版本。如有需求，在 2025 年 06 月 28 日前，您仍可以通过 Pro/deepseek-ai/DeepSeek-R1-0120 使用旧版模型，以更平滑地完成业务切换。
2025.05.23
【模型服务调整】Qwen2-1.5B 等多款模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2025 年 6 月 5 日 对下列模型进行下线处理：
Qwen/Qwen2-1.5B-Instruct
Pro/Qwen/Qwen2-1.5B-Instruct
Pro/Qwen/Qwen2-VL-7B-Instruct
THUDM/chatglm3-6b
internlm/internlm2_5-20b-chat
deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
Pro/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
若您正在使用上述任一模型，建议您尽快切换到其他模型，以免服务受到影响。
2025.04.17
【模型服务调整】HunyuanVideo（非 HD）模型停止服务
为了进一步优化资源配置，提供更先进和优质的技术服务，平台将于 2025 年 4 月 29 日 对 HunyuanVideo 模型（非 HunyuanVideo-HD）模型进行下线处理。
若您正在使用该模型，建议您尽快切换其他模型，以免服务受到影响。
2025.03.26
【模型更新】DeepSeek-V3 已升级至 0324 版本
截止目前，Pro/deepseek-ai/DeepSeek-V3 和 deepseek-ai/DeepSeek-V3 模型已经更新至最新的 0324 版本。您仍可以通过 Pro/deepseek-ai/DeepSeek-V3-1226 使用旧版模型，以更平滑地完成业务切换。
2025.03.25
【模型更新】DeepSeek-V3 将升级至 0324 版本
SiliconFlow 将启动 DeepSeek V3 模型更新。
对于 deepseek-ai/DeepSeek-V3 和 Pro/deepseek-ai/DeepSeek-V3 模型，将“逐步“更新到最新 0324 版本。
更新完成后，上述两个款模型均为 0324 版本。如有需求，在 2025 年 4 月 30 日前，您仍可以通过 deepseek-ai/DeepSeek-V3-1226 使用旧版模型，以更平滑地完成业务切换。
2025.03.11
【服务调整】api.siliconflow.com 端点将停用
为了更好的服务全球开发者用户，SiliconFlow 即将上线国际站，并逐步开设多个服务区域。
受此调整影响，现有api.siliconflow.com API端点将适时回收，请您尽快切换为api.siliconflow.cn继续使用。
我们已经为.cn端点配置了全球访问加速（GTM），使其与当前的.com端点具有相同的全球接入体验，您只需要将 API 请求的base URL修改为api.siliconflow.cn即可。
我们建议您在本月底（3 月 31 日）前完成迁移，如有任何疑问，请随时联系我们。
2025.03.07
【服务调整】DeepSeek-R1/V3 取消 RPH 和 RPD 限制
为持续提升用户体验，现调整 Rate Limits 策略如下：
去掉 deepseek-ai/DeepSeek-R1、deepseek-ai/DeepSeek-V3 的 RPH 和 RPD 限流
随着流量和负载变化，策略可能会不定时调整，硅基流动保留解释权。
2025.02.27
【模型服务调整】Marco-o1、FLUX.1 等多款模型停止服务
1. 模型下线通知
为了进一步优化资源配置，提供更先进、优质、合规的技术服务，平台将于 2025 年 3 月 6 日 对部分模型进行下线处理。
具体涉及的模型列表如下：
对话模型
AIDC-AI/Marco-o1
meta-llama/Meta-Llama-3.1-8B-Instruct
Pro/meta-llama/Meta-Llama-3.1-8B-Instruct
meta-llama/Meta-Llama-3.1-70B-Instruct
meta-llama/Meta-Llama-3.1-405B-Instruct
meta-llama/Llama-3.3-70B-Instruct
生图模型
black-forest-labs/FLUX.1-schnell
Pro/black-forest-labs/FLUX.1-schnell
black-forest-labs/FLUX.1-dev
black-forest-labs/FLUX.1-pro
stabilityai/stable-diffusion-xl-base-1.0
stabilityai/stable-diffusion-3-5-large
stabilityai/stable-diffusion-3-5-large-turbo
stabilityai/stable-diffusion-2-1
deepseek-ai/Janus-Pro-7B
语音模型
fishaudio/fish-speech-1.5
FunAudioLLM/SenseVoiceSmall
fishaudio/fish-speech-1.4
RVC-Boss/GPT-SoVITS
视频模型
Lightricks/LTX-Video
genmo/mochi-1-preview
2025.02.22
【服务调整】DeepSeek-R1/V3 新增 RPH/RPD 速率限制
为保障平台服务质量与资源合理分配，现调整Rate Limits策略如下：
一、调整内容
新增 RPH 限制（Requests Per Hour，每小时请求数）
模型范围：deepseek-ai/DeepSeek-R1、deepseek-ai/DeepSeek-V3
适用对象：所有用户
限制标准：30次/小时
新增 RPD 限制（Requests Per Day，每日请求数）
模型范围：deepseek-ai/DeepSeek-R1、deepseek-ai/DeepSeek-V3
适用对象：未完成实名认证用户
限制标准：100次/天
随着流量和负载变化，策略可能会不定时调整，硅基流动保留解释权。
2025.02.13
【模型服务调整】Yi-1.5、SD-3-medium 等多款模型停止服务
1. 模型下线通知
为了提供更稳定、高质量、可持续的服务，以下模型将于 2025 年 02 月 27 日下线：
01-ai/Yi-1.5-34B-Chat-16K
01-ai/Yi-1.5-6B-Chat
01-ai/Yi-1.5-9B-Chat-16K
stabilityai/stable-diffusion-3-medium
google/gemma-2-27b-it
google/gemma-2-9b-it
Pro/google/gemma-2-9b-it
如果您有使用上述模型，建议尽快迁移至平台上的其他模型。
2025.02.09
【价格调整】DeepSeek-V3 价格恢复原价
deepseek-ai/DeepSeek-V3 模型的价格于北京时间 2025年2月9日00:00 起恢复至原价
具体价格：
输入：¥2/ M Tokens
输出：¥8/ M Tokens
2025.02.03
【功能更新】推理模型 reasoning_content 字段分离
推理模型思维链的展示方式，从之前的 content 中的 <think></think> 独立成单独的单独的 reasoning_content 字段，兼容 OpenAI 和 deepseek api 规范，便于各个框架和上层应用在进行多轮会话时进行裁剪。使用方式详见推理模型（DeepSeek-R1）使用。
2025.02.01
【新模型上线】DeepSeek-R1 和 DeepSeek-V3 上线
支持deepseek-ai/DeepSeek-R1和deepseek-ai/DeepSeek-V3模型
具体价格如下：
deepseek-ai/DeepSeek-R1 输入：￥4/ M Tokens 输出：￥16/ M Tokens
deepseek-ai/DeepSeek-V3
即日起至北京时间 2025-02-08 24:00 享受限时折扣价：输入：¥2￥1/ M Tokens 输出：¥8￥2/ M Tokens，2025-02-09 00:00恢复原价。
2024.12.27
【服务调整】图片及视频 URL 有效期调整为 1 小时
生成图片及视频 URL 有效期调整为 1 小时
为了持续为您提供更先进、优质的技术服务，从 2025 年 1 月 20 日起，大模型生成的图片、视频 URL 有效期将调整为 1 小时。
若您正在使用图片、视频生成服务，请及时做好转存工作，避免因 URL 过期而影响业务。
2024.12.24
【价格调整】LTX-Video 模型开始计费
LTX-Video 模型即将开始计费通知
为了持续为您提供更先进、优质的技术服务，平台将于 2025 年 1 月 6 日起对 Lightricks/LTX-Video 模型的视频生成请求进行计费，价格为 0.14 元 / 视频。
2024.12.13
【模型服务调整】DeepSeek-V2-Chat 等模型停止服务
1. 模型下线通知
为了提供更稳定、高质量、可持续的服务，以下模型将于 2024 年 12 月 19 日下线：
deepseek-ai/DeepSeek-V2-Chat
Qwen/Qwen2-72B-Instruct
Vendor-A/Qwen/Qwen2-72B-Instruct
OpenGVLab/InternVL2-Llama3-76B
如果您有使用上述模型，建议尽快迁移至平台上的其他模型。
2024.12.5
【模型服务调整】Qwen2.5-Math、Hunyuan-A52B 等模型停止服务
1. 模型下线通知
为了提供更稳定、高质量、可持续的服务，以下模型将于 2024 年 12 月 13 日下线：
Qwen/Qwen2.5-Math-72B-Instruct
Tencent/Hunyuan-A52B-Instruct
如果您有使用上述模型，建议尽快迁移至平台上的其他模型。
如果您有使用上述模型，建议尽快迁移至平台上的其他模型。
2024.11.14
【模型服务调整】多款模型停止服务及相关服务更新
1. 模型下线通知
为了提供更稳定、高质量、可持续的服务，以下模型将于 2024 年 11 月 22 日下线：
deepseek-ai/DeepSeek-Coder-V2-Instruct
Qwen/Qwen2-57B-A14B-Instruct
Pro/internlm/internlm2_5-7b-chat
Pro/THUDM/chatglm3-6b
Pro/01-ai/Yi-1.5-9B-Chat-16K
Pro/01-ai/Yi-1.5-6B-Chat
如果您有使用上述模型，建议尽快迁移至平台上的其他模型。
2.邮箱登录方式更新
为进一步提升服务体验，平台将于 2024 年 11 月 22 日起调整登录方式：由原先的“邮箱账户 + 密码”方式更新为“邮箱账户 + 验证码”方式。
3. 新增海外 API 端点
新增支持海外用户的平台端点：https://api-st.siliconflow.cn。如果您在使用源端点 https://api.siliconflow.cn 时遇到网络连接问题，建议切换至新端点尝试。
2024.10.09
【价格调整】Vendor-A/Qwen2-72B 模型开始计费
为了提供更加稳定、优质、可持续的服务，Vendor-A/Qwen/Qwen2-72B-Instruct 限时免费模型将于 2024 年 10 月 17 日开始计费。计费详情如下：
限时折扣价：¥ 1.00 / M tokens
原价：¥ 4.13 / M tokens（恢复原价时间另行通知）
第三方共享信息清单和第三方 SDK 目录
更新日期：2026 年 6 月 25 日
On this page
【模型服务调整】Nex-N2-Pro、Qwen3.5-397B-A17B、MiniMax-M2.5 等模型将下线【模型价格调整】DeepSeek-V4-Flash 模型分时段定价调整【接口服务调整】/user/info 接口将停止服务【模型价格调整】DeepSeek-V4-Pro 缓存命中输入 tokens 价格调整【模型价格调整】Nex-N2-Pro、DeepSeek-V4-Pro、DeepSeek-V3.2、Qwen3.6 模型价格调整【模型服务调整】GLM-4.7、Kimi-K2.5 等模型将下线【模型服务调整】Kimi-K2、GLM-4.6 等多款模型停止服务【账户安全】未完成实名认证账户将限制使用平台功能【模型服务调整】KAT-Dev、PaddleOCR-VL 等多款模型停止服务【模型服务调整】Qwen3-Coder、ERNIE-4.5 等多款模型停止服务【模型服务调整】MiniMax-M2.1、Qwen2 等多款模型停止服务【价格调整】Qwen3.5-397B-A17B 模型定价调整【模型服务调整】MiniMax-M2、Kimi-Dev-72B 等多款模型停止服务【模型服务调整】GLM-4.5、Qwen3-235B 等模型停止服务【服务调整】平台赠送余额展示形式调整【模型升级】DeepSeek-V3.2-Exp 升级至 V3.2【模型服务调整】Ling-1T、Ring-1T 等模型停止服务【服务调整】DeepSeek-R1/V3 等模型速率限制调整【服务调整】关闭使用等级购买入口【模型服务调整】DeepSeek-V3.1 模型停止服务【模型更新】Kimi-K2-Instruct 升级至 0905 版本【模型服务调整】HunyuanVideo-HD 等视频模型停止服务【模型服务调整】DeepSeek-R1-0120 等模型停止服务【平台维护】6 月 10 日平台维护通知【模型更新】DeepSeek-R1 升级至 0528 版本【模型服务调整】Qwen2-1.5B 等多款模型停止服务【模型服务调整】HunyuanVideo（非 HD）模型停止服务【模型更新】DeepSeek-V3 已升级至 0324 版本【模型更新】DeepSeek-V3 将升级至 0324 版本【服务调整】api.siliconflow.com 端点将停用【服务调整】DeepSeek-R1/V3 取消 RPH 和 RPD 限制【模型服务调整】Marco-o1、FLUX.1 等多款模型停止服务【服务调整】DeepSeek-R1/V3 新增 RPH/RPD 速率限制【模型服务调整】Yi-1.5、SD-3-medium 等多款模型停止服务【价格调整】DeepSeek-V3 价格恢复原价【功能更新】推理模型 reasoning_content 字段分离【新模型上线】DeepSeek-R1 和 DeepSeek-V3 上线【服务调整】图片及视频 URL 有效期调整为 1 小时【价格调整】LTX-Video 模型开始计费【模型服务调整】DeepSeek-V2-Chat 等模型停止服务【模型服务调整】Qwen2.5-Math、Hunyuan-A52B 等模型停止服务【模型服务调整】多款模型停止服务及相关服务更新【价格调整】Vendor-A/Qwen2-72B 模型开始计费