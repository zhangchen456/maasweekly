<!-- url: see sources config -->
<!-- fetched: 2026-09-02T21:16:24.321019 -->

Muon 优化器的首次大规模训练实践 - Kimi API 开放平台
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
学习与支持
Muon 优化器的首次大规模训练实践
使用指南
API 接口说明
产品定价
常见问题
资源
学习与支持
Muon 优化器的首次大规模训练实践
复制页面复制页面
历史技术文章：了解 Moonlight 项目如何通过权重衰减和更新比例调整，将 Muon 优化器扩展到大模型训练。
复制页面复制页面
本文发布于 2025-03-03
近期，基于矩阵正交化（matrix orthogonalization）的 Muon 优化器在小规模语言模型训练中展现出了优异的性能，但其在大模型训练中的可扩展性尚未得到验证。我们发现了两个提升 Muon 可扩展性的关键技术：(1)引入权重衰减（weight decay）；(2)精确调整每个参数的更新比例。有了这些改进，Muon可以直接用于大规模训练，无需额外的超参数调优。扩展性实验表明，相比 AdamW，在计算量最优的训练条件下，Muon 的计算效率上实现了约 2 倍提升。
图注：Muon的扩展性验证。(a)比较Muon和Adam的扩展性实验表明，Muon的样本效率是Adam的2倍。(b)我们的Moonlight模型在MMLU上的表现与其他同类模型的对比。Moonlight在性能与训练计算量的权衡上推进了帕累托前沿。
基于这些改进，我们推出了 Moonlight 模型，这是一个使用 Muon 训练的 3B/16B 参数的混合专家模型（MoE），训练数据量达 5.7T tokens。我们的模型推进了当前的帕累托前沿（Pareto frontier），与现有模型相比，用更少的训练计算量实现了更好的性能。
我们开源了内存优化且通信高效的分布式 Muon 实现。同时，我们也发布了经过预训练、指令微调的模型检查点（checkpoints）以及中间检查点，以支持后续研究。
相关代码已在 https://github.com/MoonshotAI/Moonlight 仓库开源。 查看技术报告：Muon is Scalable for LLM Training https://arxiv.org/abs/2502.16982
​
关键要点
我们的工作在 Muon 的基础上，系统地识别并解决了其在大规模训练场景中的局限性。主要技术贡献包括：
Muon 的有效扩展性分析：通过深入分析，我们发现权重衰减在Muon的可扩展性中起着关键作用。此外，我们提出通过参数级别的更新尺度调整，来保持矩阵参数和非矩阵参数之间更新均方根（RMS）的一致性。这些调整显著提高了训练稳定性。
高效分布式实现：我们开发了采用 ZeRO-1 风格优化的分布式版 Muon，在保持算法数学特性的同时，实现了最优的内存效率和更低的通信开销。
扩展性定律（Scaling Law）验证：我们进行了扩展性研究，将 Muon 与 AdamW 的高性能基准进行对比，结果显示了Muon 的卓越性能。根据 Scaling Law 结果，Muon 在仅使用约 52% 训练计算量的情况下，就达到了与AdamW 相当的性能。
​
性能测试
我们将基于 Muon 训练的轻量级模型命名为”Moonlight”。我们将 Moonlight 与同等规模的最先进公开模型进行了对比： LLAMA3-3B 是一个使用 9 万亿 tokens 训练的 30 亿参数密集模型 Qwen2.5-3B 是一个使用 18 万亿 tokens 训练的 30 亿参数密集模型 Deepseek-v2-Lite 是一个使用 5.7 万亿 tokens 训练的 2.4 亿/ 160 亿参数混合专家模型
注：Qwen 2和2.5的报告中未披露其优化器信息。†报告的参数数量不包括嵌入层参数。‡我们使用完整的TriviaQA数据集测试了所有列出的模型。
​
使用示例
​
模型下载
|
| Model | #Total Params | #Activated Params | Context Length | Download Link
| Moonlight | 16B | 3B | 8K | 🤗 Hugging Face
| Moonlight-Instruct | 16B | 3B | 8K | 🤗 Hugging Face
​
用Hugging Face Transformers进行推理
我们将介绍如何使用transformers库在推理阶段使用我们的模型。建议使用python=3.10、torch>=2.1.0和transformers=4.48.2作为开发环境。
对于我们的预训练模型（Moonlight）：
from transformers import AutoModelForCausalLM, AutoTokenizer
model_path = "moonshotai/Moonlight-16B-A3B"
model = AutoModelForCausalLM.from_pretrained(
model_path,
torch_dtype="auto",
device_map="auto",
trust_remote_code=True,
)
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
prompt = "1+1=2, 1+2="
inputs = tokenizer(prompt, return_tensors="pt", padding=True, truncation=True).to(model.device)
generated_ids = model.generate(**inputs, max_new_tokens=100)
response = tokenizer.batch_decode(generated_ids)[0]
print(response)
对于我们的指令模型（Moonlight-Instruct）：
from transformers import AutoModelForCausalLM, AutoTokenizer
model_path = "moonshotai/Moonlight-16B-A3B-Instruct"
model = AutoModelForCausalLM.from_pretrained(
model_path,
torch_dtype="auto",
device_map="auto",
trust_remote_code=True
)
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
messages = [
{"role": "system", "content": "You are a helpful assistant provided by Moonshot-AI."},
{"role": "user", "content": "Is 123 a prime?"}
]
input_ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
generated_ids = model.generate(inputs=input_ids, max_new_tokens=500)
response = tokenizer.batch_decode(generated_ids)[0]
print(response)
Moonlight 采用与DeepSeek-V3相同的架构，这一架构受到许多主流推理引擎的支持，如VLLM和SGLang。因此，我们的模型也可以轻松地使用这些工具进行部署。
​
训练代码
# train qwen-like dense model with muon
python3 examples/toy_train.py --model qwen --optimizer muon --dataset openwebtext-100k --hidden_size 896 --lr 1e-3
# train qwen-like dense model with adamw
python3 examples/toy_train.py --model qwen --optimizer adamw --dataset openwebtext-100k --hidden_size 896 --lr 1e-3
​
中间检查点
我们已经发布了Moonlight和Moonlight-A的中间检查点（checkpoint）以支持进一步的研究工作： https://github.com/MoonshotAI/Moonlight/blob/master/Moonlight_intermediate_checkpoints.pdf
一些亮点：
我们可以看到使用 Muon 训练的 Moonlight 模型在数学和编程方面的表现优于使用AdamW训练的Moonlight-A。
我们还可以分析 Moonlight 和 Moonlight-A 中间检查点在 SVD Entropy 和 Srank 方面的不同表现。
​
引用
如果您觉得 Moonlight 有用或想在您的项目中使用它，请引用我们的论文：
@misc{liu2025muonscalablellmtraining,
title={Muon is Scalable for LLM Training},
author={Jingyuan Liu and Jianlin Su and Xingcheng Yao and Zhejun Jiang and Guokun Lai and Yulun Du and Yidao Qin and Weixin Xu and Enzhe Lu and Junjie Yan and Yanru Chen and Huabin Zheng and Yibo Liu and Shaowei Liu and Bohong Yin and Weiran He and Han Zhu and Yuzhi Wang and Jianzhou Wang and Mengnan Dong and Zheng Zhang and Yongsheng Kang and Hao Zhang and Xinran Xu and Yutao Zhang and Yuxin Wu and Xinyu Zhou and Zhilin Yang},
year={2025},
eprint={2502.16982},
archivePrefix={arXiv},
primaryClass={cs.LG},
url={https://arxiv.org/abs/2502.16982},
}
了解更多： Muon优化器赏析：从向量到矩阵的本质跨越（By 苏剑林） https://kexue.fm/archives/10592
Muon续集：为什么我们选择尝试Muon？（By 苏剑林） https://kexue.fm/archives/10739
此页面对您有帮助吗？
是
否