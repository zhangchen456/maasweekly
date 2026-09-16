<!-- url: see sources config -->
<!-- fetched: 2026-09-16T13:12:57.569175 -->

Release Notes | Cohere
For AI agents: a documentation index is available at the root level at /llms.txt. Append /llms.txt to any URL for a page-level index, or .md for the markdown version of any page.
docs
v2 API
v2 API
Search
/Ask AI
Guides and conceptsAPI ReferenceRelease NotesLLMUCookbooks
Search
/Ask AI
v2 API
v2 API
Guides and concepts
API Reference
Release Notes
LLMU
Cookbooks
DASHBOARDPLAYGROUNDDOCSCOMMUNITYLOG IN
Light
On this page
September 9, 2026
Key features
Technical details
Availability
August 27, 2026
Availability
July 7, 2026
Technical Details
Availability
June 9, 2026
Technical Details
Availability
May 20, 2026
Key Features
Technical Details
Availability
April 4, 2026
Retirement notice
March 26, 2026
Technical details
Getting started
Availability
December 11, 2025
Technical Details
Example Query
August 28, 2025
Key Features
Getting Started
Availability
Release Notes
Subscribe via RSS
September 9, 2026
September 9, 2026
August 27, 2026
August 27, 2026
July 7, 2026
July 7, 2026
June 9, 2026
June 9, 2026
May 20, 2026
May 20, 2026
April 4, 2026
April 4, 2026
March 26, 2026
March 26, 2026
December 11, 2025
December 11, 2025
September 16, 2025
September 16, 2025
August 28, 2025
August 28, 2025
Announcing Cohere's North Small Translate
We’re pleased to announce the release of
North Small Translate, an open-weights mixture-of-experts model purpose-built
for machine translation across more than 50 languages.
North Small Translate is designed to give researchers, developers, and enterprises flexible ways to evaluate and
deploy machine translation while retaining control over their data and infrastructure.
Key features
Purpose-built translation: Optimized for machine translation across more than 50 languages and locale
variants.
Efficient MoE architecture: 218 billion total parameters with 25 billion active parameters.
Flexible deployment: Available through the free-tier Chat V2 API, as FP8 open weights for non-commercial
use, and through Model Vault with a commercial license.
Private deployment: Suggested deployment hardware is two H100 GPUs or one B200 GPU.
Technical details
Model name: north-small-translate-1-0
Context length: 16K
License:
Creative Commons Attribution-NonCommercial 4.0
Open-weights format: FP8
Availability
North Small Translate is available on the free tier through the Chat V2 API. The
FP8 weights
are available on Hugging Face
for non-commercial use under the CC BY-NC 4.0 license.
For production use, enterprises can purchase a commercial license and deploy North Small Translate through
Model Vault.
For supported languages, use cases, and an API example, see the
model documentation.
Meet Cohere Parse
Today we are releasing Cohere Parse.
Parse (model ID: parse-v5.0) turns complex documents into clean, structured Markdown ready for downstream AI workflows. The 2.3B-parameter multimodal model extracts text in reading order, tables, lists, forms, images and captions, page boundaries, and visual element locations.
Outputs include Markdown/HTML content, HTML-formatted tables, bounding boxes, and image descriptions — preserving both document structure and layout for easier rendering and processing.
Key specs: 8K context window · ~4.6GB model size · Markdown output
Availability
Cohere Parse is available through the Parse API, as well as Microsoft Foundry
and AWS SageMaker
.
For single-tenant deployment, Parse is also available in Model Vault.
For more details, see the model documentation.
Meet Cohere Transcribe Arabic
Today we are releasing Cohere Transcribe Arabic.
This open-source speech-to-text model is a fine-tune of Cohere Transcribe using Arabic speech data. It
lets Arabic speakers transcribe their voice with unmatched accuracy and support for regional dialects or
speech patterns.
It is currently the most accurate open-source Arabic ASR model available today and is optimized for
production inference and throughput.
Technical Details
Model Name: cohere-transcribe-arabic-07-2026
Size: 2B
Architecture: conformer-based encoder-decoder
Languages supported: Arabic (all major dialects), English (including English spoken with an
Arabic accent)
License: Apache 2.0
Availability
Cohere Transcribe Arabic is available through the V2 Audio Transcriptions API and as open weights on
Hugging Face
. For
production use, Model Vault deployment is also supported.
For more details, see the model documentation.
Announcing Cohere's North Mini Code
We’re pleased to announce the release of North Mini Code, Cohere’s first
agentic coding model. It is a 30 billion total / 3 billion active parameter Mixture of Experts model
trained specifically for agentic coding, with a small enough active footprint to run on local hardware.
Technical Details
Model Name: north-mini-code-1-0
Context Length: 256K input, 64K output
License: Apache 2.0
Availability
North Mini Code is available through the Chat V2 API and as open weights on Hugging Face. For
production use, Model Vault deployment is also supported.
For more details, see the model documentation.
Announcing Cohere’s Command A+
We’re pleased to announce the release of Command A+, the last model in the Command A
family of models, combining support for vision inputs, reasoning capabilities, translation capabilities, and
agentic tasks all within the same model. It is also notably our first Mixture of Experts (MoE) model with 25
billion active parameters ands 218 billion total parameters.
Key Features
Agentic Applications: With notable performance increases in tool use and agentic tasks, Command A+ is
the strongest agentic model in the Command family.
Expanded Multilingual Support: With 48 languages supported, including all official EU languages, this
more than doubles the support of languages from our prior models.
Efficient & Fast: With as few as 1 x B200 or 2 x H100s required to deploy the model, and up to 110%
throughput increase and 30% decrease in latency over Command A Reasoning, the model is designed for
production-grade deployments.
Technical Details
Model Name: command-a-plus-05-2026
Context Length: 128K input, 64K output
Languages covered: English, Arabic, Bulgarian, Bengali, Catalan, Czech, Danish, German, Greek, Spanish, Estonian, Persian, Finnish, Filipino, French, Irish, Hebrew, Hindi, Croatian, Hungarian, Indonesian, Icelandic, Italian, Japanese, Korean, Lithuanian, Latvian, Malay, Maltese, Dutch, Norwegian, Punjabi, Polish, Portuguese, Romanian, Russian, Slovak, Slovenian, Serbian, Swedish, Tamil, Telugu, Thai, Turkish, Ukrainian, Urdu, Vietnamese, Chinese.
License: Apache 2.0
Availability
Command A+ (command-a-plus-05-2026) is now available for all Cohere users through our standard API
endpoints. For enterprise customers, private deployment options are
available to ensure maximum security and control over your translation workflows.
For more detailed information about Command A+, including technical specifications and implementation
examples, visit our model documentation.
Retirement of Embed v2.0 and Aya Expanse / Vision 8B
Retirement notice
Effective April 4, 2026, the following models are no longer available. Requests using these model IDs will fail.
Retired models:
embed-english-v2.0
embed-english-light-v2.0
embed-multilingual-v2.0
c4ai-aya-expanse-8b
c4ai-aya-vision-8b
We recommend these replacements:
Embedding tasks
embed-english-v3.0
embed-multilingual-v3.0
embed-v4.0
Chat tasks
command-r7b-12-2024
command-a-03-2025
command-a-reasoning-08-2025
For the full announcement and lifecycle context, see the Deprecations page. For questions or
assistance, contact support@cohere.com
.
Announcing the Cohere Transcribe model
We’re pleased to announce the release of Cohere Transcribe, our first transcription model.
Cohere Transcribe specializes in audio-in, text-out, automatic speech recognition (ASR).
Technical details
Model name: cohere-transcribe-03-2026
Input: Audio waveform
Output: Text
Languages covered: English, German, French, Italian, Spanish, Portuguese, Greek, Dutch, Polish,
Vietnamese, Chinese, Arabic, Japanese, Korean.
License: Apache 2.0
API endpoint: Audio Transcriptions API
Getting started
The model is available immediately through Cohere’s Audio Transcriptions API endpoint.
You can start transcribing audio using the following example query:
PYTHON
import cohere
co = cohere.ClientV2()
response = co.audio.transcriptions.create(
model="cohere-transcribe-03-2026",
language="en",
file=open("./sample.wav", "rb"),
)
print(response)
Availability
You can access Cohere Transcribe via our API
for free, low-setup experimentation
subject to rate limits. See the Different Types of API Keys and Rate Limits page for
usage details and integration guidance.
For production deployment without rate limits, provision a dedicated Model Vault.
This enables low-latency, private cloud inference without having to manage infrastructure. Pricing is
calculated per hour-instance, with discounted plans for longer-term commitments.
Contact our team
to discuss your requirements.
Cohere's Rerank v4.0 Model is Here!
We’re pleased to announce the release of Rerank 4.0 our newest and most performant foundational model for ranking.
Technical Details
Two model variants available:
rerank-v4.0-pro: Optimized for state-of-the-art quality and complex use-cases
rerank-v4.0-fast: Optimized for low latency and high throughput use-cases
Multilingual support: Re-rank both English and non-English documents
Semi-structured data support: Re-rank JSON documents
Extended context length: 32k token context window
Example Query
PYTHON
import cohere
co = cohere.ClientV2()
query = "What is the capital of the United States?"
docs = [
"Carson City is the capital city of the American state of Nevada. At the 2010 United States Census, Carson City had a population of 55,274.",
"The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean that are a political division controlled by the United States. Its capital is Saipan.",
"Charlotte Amalie is the capital and largest city of the United States Virgin Islands. It has about 20,000 people. The city is on the island of Saint Thomas.",
"Washington, D.C. (also known as simply Washington or D.C., and officially as the District of Columbia) is the capital of the United States. It is a federal district. The President of the USA and many major national government offices are in the territory. This makes it the political center of the United States of America.",
"Capital punishment has existed in the United States since before the United States was a country. As of 2017, capital punishment is legal in 30 of the 50 states. The federal government (including the United States military) also uses capital punishment.",
]
results = co.rerank(
model="rerank-v4.0-pro", query=query, documents=docs, top_n=5
)
Announcing Major Command Deprecations
As part of our ongoing commitment to delivering advanced AI solutions, we are deprecating the following models, features, and API endpoints:
Deprecated Models:
command-r-03-2024 (and the alias command-r)
command-r-plus-04-2024 (and the alias command-r-plus)
command-light
command
summarize (Refer to the migration guide
for alternatives).
For command model replacements, we recommend you use command-r-08-2024, command-r-plus-08-2024, or command-a-03-2025 (which is the strongest-performing model across domains) instead.
Retired Fine-Tuning Capabilities:
All fine-tuning options via dashboard and API for models including command-light, command, command-r, classify, and rerank are being retired. Previously fine-tuned models will no longer be accessible.
Deprecated Features and API Endpoints:
/v1/connectors (Managed connectors for RAG)
/v1/chat parameters: connectors, search_queries_only
/v1/generate (Legacy generative endpoint)
/v1/summarize (Legacy summarization endpoint)
/v1/classify
Slack App integration
Coral Web UI (chat.cohere.com and coral.cohere.com)
For questions, reach out to support@cohere.com
Announcing Cohere's Command A Translate Model
We’re excited to announce the release of Command A Translate, Cohere’s first machine translation model. It achieves state-of-the-art performance at producing accurate, fluent translations across 23 languages.
Key Features
23 supported languages: English, French, Spanish, Italian, German, Portuguese, Japanese, Korean, Chinese, Arabic, Russian, Polish, Turkish, Vietnamese, Dutch, Czech, Indonesian, Ukrainian, Romanian, Greek, Hindi, Hebrew, and Persian
111 billion parameters for superior translation quality
16K token context length (8K input + 8K output) for handling longer texts
Optimized for deployment on 1-2 GPUs (A100s/H100s)
Secure deployment options for sensitive data translation
Getting Started
The model is available immediately through Cohere’s Chat API endpoint. You can start translating text with simple prompts or integrate it programmatically into your applications.
from cohere import ClientV2
co = ClientV2(api_key="<YOUR API KEY>")
response = co.chat(
model="command-a-translate-08-2025",
messages=[
{
"role": "user",
"content": "Translate this text to Spanish: Hello, how are you?",
}
],
)
Availability
Command A Translate (command-a-translate-08-2025) is now available for all Cohere users through our standard API endpoints. For enterprise customers, private deployment
options are available to ensure maximum security and control over your translation workflows.
For more detailed information about Command A Translate, including technical specifications and implementation examples, visit our model documentation.self.__next_f.push([1,"43:I[615584,[\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmgppy6c_mh8.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/230d0ta35d95a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1fu5zu3p0kax4.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3h8wc6jlok0kt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2keyjoxe_xpyt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0o_h6ac3pa-9q.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0x59_mzmzmxy6.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/03w70glgr4690.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3kddk--7sseol.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1keb3ycmkfwgt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31s2f1csvea5a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1cue2ugdfepfm.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/14gxuylmt2jhv.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1mhmig4b1nvft.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/04c22f6nktp2g.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/238davtl8og_7.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2mjo6z0-su8u9.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3p9tk099xipyj.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/19xybe_p57542.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0esapfjuyc4yz.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1366d9n7dkhd2.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/02dgkrr20pus_.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3pv4qy5i1r4hf.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/42izzc1yovais.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmj3tesniy-f.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1r8x8gbl6axdq.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31u8ypko2q4if.js\"],\"ConsoleMessage\"]\n44:I[606010,[\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmgppy6c_mh8.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/230d0ta35d95a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1fu5zu3p0kax4.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3h8wc6jlok0kt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2keyjoxe_xpyt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0o_h6ac3pa-9q.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0x59_mzmzmxy6.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/03w70glgr4690.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3kddk--7sseol.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1keb3ycmkfwgt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31s2f1csvea5a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1cue2ugdfepfm.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/14gxuylmt2jhv.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1mhmig4b1nvft.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/04c22f6nktp2g.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/238davtl8og_7.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2mjo6z0-su8u9.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3p9tk099xipyj.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/19xybe_p57542.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0esapfjuyc4yz.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1366d9n7dkhd2.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/02dgkrr20pus_.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3pv4qy5i1r4hf.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/42izzc1yovais.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmj3tesniy-f.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1r8x8gbl6axdq.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31u8ypko2q4if.js\"],\"ScrollToTop\"]\n45:I[140440,[\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmgppy6c_mh8.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/230d0ta35d95a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1fu5zu3p0kax4.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3h8wc6jlok0kt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2keyjoxe_xpyt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0o_h6ac3pa-9q.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0x59_mzmzmxy6.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/03w70glgr4690.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3kddk--7sseol.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1keb3ycmkfwgt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31s2f1csvea5a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1cue2ugdfepfm.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/14gxuylmt2jhv.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1mhmig4b1nvft.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/04c22f6nktp2g.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/238davtl8og_7.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2mjo6z0-su8u9.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3p9tk099xipyj.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/19xybe_p57542.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0esapfjuyc4yz.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1366d9n7dkhd2.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/02dgkrr20pus_.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3pv4qy5i1r4hf.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/42izzc1yovais.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmj3tesniy-f.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1r8x8gbl6axdq.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31u8ypko2q4if.js\"],\"Providers\"]\n46:I[82264,[\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmgppy6c_mh8.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/230d0ta35d95a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1fu5zu3p0kax4.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3h8wc6jlok0kt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2keyjoxe_xpyt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0o_h6ac3pa-9q.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0x59_mzmzmxy6.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/03w70glgr4690.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3kddk--7sseol.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1keb3ycmkfwgt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31s2f1csvea5a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1cue2ugdfepfm.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/14gxuylmt2jhv.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1mhmig4b1nvft.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/04c22f6nktp2g.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/238davtl8og_7.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2mjo6z0-su8u9.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3p9tk099xipyj.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/19xybe_p57542.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0esapfjuyc4yz.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1366d9n7dkhd2.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/02dgkrr20pus_.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3pv4qy5i1r4hf.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/42izzc1yovais.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmj3tesniy-f.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1r8x8gbl6axdq.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31u8ypko2q4if.js\"],\"FernThemeProvider\"]\n47:I[946367,[\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmgppy6c_mh8.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/230d0ta35d95a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1fu5zu3p0kax4.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3h8wc6jlok0kt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2keyjoxe_xpyt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0o_h6ac3pa-9q.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0x59_mzmzmxy6.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/03w70glgr4690.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3kddk--7sseol.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1keb3ycmkfwgt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31s2f1csvea5a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1cue2ugdfepfm.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/14gxuylmt2jhv.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1mhmig4b1nvft.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/04c22f6nktp2g.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/238davtl8og_7.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2mjo6z0-su8u9.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3p9tk099xipyj.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/19xybe_p57542.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0esapfjuyc4yz.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1366d9n7dkhd2.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/02dgkrr20pus_.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3pv4qy5i1r4hf.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/42izzc1yovais.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmj3tesniy-f.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1r8x8gbl6axdq.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31u8ypko2q4if.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/37rfj5f53d5x2.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2o3sqtcfn0vy3.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0l16ua9yis59z.js\"],\"RootNodeProvider\"]\n49:I[621632,[\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmgppy6c_mh8.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/230d0ta35d95a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1fu5zu3p0kax4.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3h8wc6jlok0kt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2keyjoxe_xpyt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0o_h6ac3pa-9q.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0x59_mzmzmxy6.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/03w70glgr4690.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3kddk--7sseol.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1keb3ycmkfwgt.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31s2f1csvea5a.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1cue2ugdfepfm.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/14gxuylmt2jhv.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1mhmig4b1nvft.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/04c22f6nktp2g.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/238davtl8og_7.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/2mjo6z0-su8u9.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3p9tk099xipyj.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/19xybe_p57542.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0esapfjuyc4yz.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1366d9n7dkhd2.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/02dgkrr20pus_.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/3pv4qy5i1r4hf.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/42izzc1yovais.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/0xmj3tesniy-f.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/1r8x8gbl6axdq.js\",\"https://app.buildwithfern.com/_next/static/immutable/chunks/31u8ypko2q4if.js\"],\"HydrateServerState\"]\n48:[]\n42:[\"$\",\"body\",null,{\"className\":\"antialiased\",\"id\":\"fern-docs\",\"children\":[[\"$\",\"script\",null,{\"dangerouslySetInnerHTML\":{\"__html\":\"(function(){window.__FERN_PRE_HYDRATION_HTML=document.body.innerHTML})()\"}}],[\"$\",\"script\",null,{\"dangerouslySetInnerHTML\":{\"__html\":\"(function(){var f=self.__next_f=self.__next_f||[];var p=[].push;Object.defineProperty(f,\\\"push\\\",{configurable:true,get:function(){return function(){try{return p.apply(f,arguments)}catch(e){if(e instanceof TypeError\u0026\u0026e.message.indexOf(\\\"enqueue\\\")!==-1)return;throw e}}},set:function(v){p=v}})})()\"}}],[\"$\",\"$L43\",null,{\"isWhitelabeled\":false}],[\"$\",\"$L44\",null,{}],[\"$\",\"div\",null,{\"className\":\"sr-only\",\"aria-hidden\":\"true\",\"inert\":true,\"children\":\"For AI agents: a documentation index is available at the root level at /llms.txt. Append /llms.txt to any URL for a page-level index, or .md for the markdown version of any page.\"}],false,[\"$\",\"$L45\",null,{\"children\":[\"$\",\"$L46\",null,{\"hasLight\":true,\"hasDark\":true,\"lightThemeColor\":\"#e8e6de\",\"darkThemeColor\":\"#0f0f0f\",\"children\":[\"$\",\"$L47\",null,{\"sidebarRootNodesToChildToParentsMap\":\"$Q48\",\"children\":[[\"$\",\"$L49\",null,{\"domain\":\"docs.cohere.com\",\"basePath\":\"/\",\"cdnOrigin\":\"https://app.buildwithfern.com\",\"logoText\":\"docs\",\"defaultLanguage\":\"python\",\"isPrintView\":false,\"darkModeCode\":false,\"isWhitelabeled\":false,\"isAirgapped\":false,\"isDiscriminatedUnionDropdownEnabled\":false,\"colors\":{\"light\":{\"logo\":{\"src\":\"https://fdr-prod-docs-files-public.s3.us-east-1.amazonaws.com/cohere.docs.buildwithfern.com/db6fc38b64e45824e93041fc459409dec34f01263d0fc313f88fe6d14e981714/assets/logo.svg?X-Amz-Algorithm=AWS4-HMAC-SHA256\u0026X-Amz-Content-Sha256=UNSIGNED-PAYLOAD\u0026X-Amz-Credential=AKIA6KXJSKKNFOCF7G4B%2F20260915%2Fus-east-1%2Fs3%2Faws4_request\u0026X-Amz-Date=20260915T230844Z\u0026X-Amz-Expires=604800\u0026X-Amz-Signature=e773c07becc93f273f81c4905bd3cdf803a99ee51addcb09f5e505d8111ff093\u0026X-Amz-SignedHeaders=host\u0026x-amz-checksum-mode=ENABLED\u0026x-id=GetObject\",\"contentType\":\"image/svg+xml\",\"width\":96,\"height\":16,\"blurDataURL\":\"$undefined\"},\"backgroundImage\":\"$undefined\",\"appearance\":\"light\",\"accentScale\":[\"#e0e2e1\",\"#d9dddb\",\"#cad5d0\",\"#bcccc5\",\"#aec3ba\",\"#9fb8ae\",\"#8daa9e\",\"#729687\",\"#39594d\",\"#2a4a3e\",\"#2c4c40\",\"#1e2f28\"],\"accentScaleAlpha\":[\"#94bcfe18\",\"#0760b111\",\"#01637221\",\"#045f5c31\",\"#015b4f40\",\"#03564751\",\"#034f3d65\",\"#00493382\",\"#012c1fc1\",\"#00281bd1\",\"#00291bcf\",\"#01150edf\"],\"accentScaleWideGamut\":[\"oklch(91.1% 0.0028 168.8)\",\"oklch(89.4% 0.0055 168.8)\",\"oklch(86.3% 0.0133 168.8)\",\"oklch(83.2% 0.0203 168.8)\",\"oklch(79.9% 0.0258 168.8)\",\"oklch(76.1% 0.0307 168.8)\",\"oklch(71.2% 0.036 168.8)\",\"oklch(64.1% 0.0454 168.8)\",\"oklch(43.5% 0.0428 168.8)\",\"oklch(37.9% 0.0428 168.8)\",\"oklch(38.7% 0.0428 168.8)\",\"oklch(28.7% 0.0245 168.8)\"],\"accentScaleAlphaWideGamut\":[\"color(display-p3 0.4157 0.6549 1 / 0.063)\",\"color(display-p3 0.0118 0.3255 0.6196 / 0.061)\",\"color(display-p3 0.0039 0.3529 0.3922 / 0.121)\",\"color(display-p3 0.0039 0.3059 0.298 / 0.177)\",\"color(display-p3 0.0039 0.298 0.2549 / 0.233)\",\"color(display-p3 0.0039 0.2784 0.2353 / 0.294)\",\"color(display-p3 0.0039 0.251 0.1922 / 0.367)\",\"color(display-p3 0.0039 0.2392 0.1647 / 0.479)\",\"color(display-p3 0 0.1373 0.0902 / 0.725)\",\"color(display-p3 0 0.1216 0.0784 / 0.789)\",\"color(display-p3 0 0.1255 0.0824 / 0.781)\",\"color(display-p3 0 0.0588 0.0314 / 0.854)\"],\"accentContrast\":\"#fff\",\"grayScale\":[\"#fdfdfc\",\"#f9f9f8\",\"#f1f0ef\",\"#e9e8e6\",\"#e2e1de\",\"#dad9d6\",\"#cfceca\",\"#bcbbb5\",\"#8d8d86\",\"#82827c\",\"#63635e\",\"#21201c\"],\"grayScaleAlpha\":[\"#55550003\",\"#25250007\",\"#20100010\",\"#1f150019\",\"#1f180021\",\"#19130029\",\"#19140035\",\"#1915014a\",\"#0f0f0079\",\"#0c0c0083\",\"#080800a1\",\"#060500e3\"],\"grayScaleWideGamut\":[\"color(display-p3 0.992 0.992 0.989)\",\"color(display-p3 0.977 0.977 0.973)\",\"color(display-p3 0.943 0.942 0.936)\",\"color(display-p3 0.913 0.912 0.903)\",\"color(display-p3 0.885 0.883 0.873)\",\"color(display-p3 0.854 0.852 0.839)\",\"color(display-p3 0.813 0.81 0.794)\",\"color(display-p3 0.738 0.734 0.713)\",\"color(display-p3 0.553 0.553 0.528)\",\"color(display-p3 0.511 0.511 0.488)\",\"color(display-p3 0.388 0.388 0.37)\",\"color(display-p3 0.129 0.126 0.111)\"],\"grayScaleAlphaWideGamut\":[\"#55550003\",\"#25250007\",\"#20100010\",\"#1f150019\",\"#1f180021\",\"#19130029\",\"#19140035\",\"#1915014a\",\"#0f0f0079\",\"#0c0c0083\",\"#080800a1\",\"#060500e3\"],\"graySurface\":\"#ffffffcc\",\"graySurfaceWideGamut\":\"color(display-p3 1 1 1 / 80%)\",\"accentSurface\":\"#d6dbdbcc\",\"accentSurfaceWideGamut\":\"color(display-p3 0.8392 0.8588 0.8549 / 0.8)\",\"background\":\"rgba(232, 230, 222, 1)\",\"accent\":\"rgba(57, 89, 77, 1)\",\"border\":\"rgba(224, 224, 224, 1)\",\"sidebarBackground\":\"rgba(250, 250, 250, 1)\",\"headerBackground\":\"rgba(250, 250, 250, 1)\",\"sidebarBackgroundTheme\":\"light\",\"headerBackgroundTheme\":\"light\",\"cardBackground\":\"rgba(255, 255, 255, 1)\",\"themeColor\":\"#e8e6de\",\"backgroundGradient\":false},\"dark\":{\"logo\":{\"src\":\"https://fdr-prod-docs-files-public.s3.us-east-1.amazonaws.com/cohere.docs.buildwithfern.com/f27fafd7fd7bee4204f14f4e576c6c7f5c6951e652cb030a1a6c883d3fe1f0dc/assets/logo-dark.svg?X-Amz-Algorithm=AWS4-HMAC-SHA256\u0026X-Amz-Content-Sha256=UNSIGNED-PAYLOAD\u0026X-Amz-Credential=AKIA6KXJSKKNFOCF7G4B%2F20260915%2Fus-east-1%2Fs3%2Faws4_request\u0026X-Amz-Date=20260915T230844Z\u0026X-Amz-Expires=604800\u0026X-Amz-Signature=99bb8da2fdbaa8b60c2aaf783502ad2ddbae5cb0e20c520a4565035ffddb5b90\u0026X-Amz-SignedHeaders=host\u0026x-amz-checksum-mode=ENABLED\u0026x-id=GetObject\",\"contentType\":\"image/svg+xml\",\"width\":96,\"height\":16,\"blurDataURL\":\"$undefined\"},\"backgroundImage\":\"$undefined\",\"appearance\":\"dark\",\"accentScale\":[\"#0c100e\",\"#131917\",\"#1a2a23\",\"#1e372d\",\"#284439\",\"#335246\",\"#416355\",\"#4f7968\",\"#517b6a\",\"#496c5e\",\"#9bc7b4\",\"#ceefe0\"],\"accentScaleAlpha\":[\"#008f0002\",\"#6cf7c90b\",\"#70fdbf1d\",\"#68fdc12b\",\"#7ffccb39\",\"#8ffdd248\",\"#9dfdd55a\",\"#a0ffd871\",\"#a2ffd973\",\"#a5ffdb63\",\"#c6ffe6c4\",\"#dcffefee\"],\"accentScaleWideGamut\":[\"oklch(16.8% 0.0075 167.1)\",\"oklch(20.8% 0.0107 167.1)\",\"oklch(26.8% 0.0245 167.1)\",\"oklch(31.3% 0.0358 167.1)\",\"oklch(35.9% 0.0396 167.1)\",\"oklch(41% 0.0419 167.1)\",\"oklch(47% 0.0461 167.1)\",\"oklch(53.9% 0.054 167.1)\",\"oklch(54.7% 0.054 167.1)\",\"oklch(50% 0.0461 167.1)\",\"oklch(79.3% 0.054 167.1)\",\"oklch(92.4% 0.039 167.1)\"],\"accentScaleAlphaWideGamut\":[\"color(display-p3 0 0.8431 0 / 0.005)\",\"color(display-p3 0.5294 0.9961 0.8078 / 0.042)\",\"color(display-p3 0.5451 0.9961 0.7529 / 0.113)\",\"color(display-p3 0.5647 0.9961 0.8039 / 0.163)\",\"color(display-p3 0.6196 1 0.8392 / 0.217)\",\"color(display-p3 0.6745 1 0.8588 / 0.275)\",\"color(display-p3 0.7059 1 0.8667 / 0.346)\",\"color(display-p3 0.7137 1 0.8667 / 0.438)\",\"color(display-p3 0.7216 1 0.8706 / 0.446)\",\"color(display-p3 0.7333 1 0.8784 / 0.384)\",\"color(display-p3 0.8235 0.9961 0.9098 / 0.763)\",\"color(display-p3 0.8902 1 0.9451 / 0.93)\"],\"accentContrast\":\"#fff\",\"grayScale\":[\"#111111\",\"#191919\",\"#222222\",\"#2a2a2a\",\"#313131\",\"#3a3a3a\",\"#484848\",\"#606060\",\"#6e6e6e\",\"#7b7b7b\",\"#b4b4b4\",\"#eeeeee\"],\"grayScaleAlpha\":[\"#00000000\",\"#ffffff09\",\"#ffffff12\",\"#ffffff1b\",\"#ffffff22\",\"#ffffff2c\",\"#ffffff3b\",\"#ffffff55\",\"#ffffff64\",\"#ffffff72\",\"#ffffffaf\",\"#ffffffed\"],\"grayScaleWideGamut\":[\"color(display-p3 0.067 0.067 0.067)\",\"color(display-p3 0.098 0.098 0.098)\",\"color(display-p3 0.135 0.135 0.135)\",\"color(display-p3 0.163 0.163 0.163)\",\"color(display-p3 0.192 0.192 0.192)\",\"color(display-p3 0.228 0.228 0.228)\",\"color(display-p3 0.283 0.283 0.283)\",\"color(display-p3 0.375 0.375 0.375)\",\"color(display-p3 0.431 0.431 0.431)\",\"color(display-p3 0.484 0.484 0.484)\",\"color(display-p3 0.706 0.706 0.706)\",\"color(display-p3 0.933 0.933 0.933)\"],\"grayScaleAlphaWideGamut\":[\"#00000000\",\"#ffffff09\",\"#ffffff12\",\"#ffffff1b\",\"#ffffff22\",\"#ffffff2c\",\"#ffffff3b\",\"#ffffff55\",\"#ffffff64\",\"#ffffff72\",\"#ffffffaf\",\"#ffffffed\"],\"graySurface\":\"rgba(0, 0, 0, 0.05)\",\"graySurfaceWideGamut\":\"color(display-p3 0 0 0 / 5%)\",\"accentSurface\":\"#17231f80\",\"accentSurfaceWideGamut\":\"color(display-p3 0.0941 0.1333 0.1176 / 0.5)\",\"background\":\"rgba(15, 15, 15, 1)\",\"accent\":\"rgba(81, 123, 106, 1)\",\"border\":\"rgba(41, 41, 41, 1)\",\"sidebarBackground\":\"rgba(28, 28, 28, 1)\",\"headerBackground\":\"rgba(28, 28, 28, 1)\",\"sidebarBackgroundTheme\":\"dark\",\"headerBackgroundTheme\":\"dark\",\"cardBackground\":\"rgba(0, 0, 0,