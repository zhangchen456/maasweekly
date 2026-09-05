<!-- url: see sources config -->
<!-- fetched: 2026-09-05T09:03:20.025499 -->

Vertex AI release notes  |  Generative AI on Vertex AI  |  Google Cloud Documentation
Skip to main content
/
Console
English
Deutsch
Español – América Latina
Français
Português – Brasil
中文 – 简体
日本語
한국어
Sign in
Vertex AI
Generative AI on Vertex AI
Start free
Vertex AI documentation is no longer being updated
Vertex AI's services are now part of Gemini Enterprise Agent Platform. See the most up-to-date information in the Agent Platform documentation.
Home
Documentation
AI and ML
Vertex AI
Generative AI on Vertex AI
Resources
Send feedback
Vertex AI release notes
Stay organized with collections
Save and categorize content based on your preferences.
This page documents production updates to Vertex AI.
Check this page for announcements about new or updated features, bug fixes,
known issues, and deprecated functionality.
You can see the latest product updates for all of Google Cloud on the
Google Cloud page, browse and filter all release notes in the
Google Cloud console,
or programmatically access release notes in
BigQuery.
To get the latest product updates delivered to you, add the URL of this page to your
feed
reader, or add the
feed URL directly.
May 26, 2026
Deprecated
Vertex AI Extensions deprecation
Vertex AI Extensions is deprecated and will be shut down after November 26, 2026.
We recommend
migrating to Agent Platform
to avoid service disruption.
April 17, 2026
Feature
RAG Cross Corpus Retrieval
RAG Cross Corpus Retrieval is available in public preview. This feature allows you to retrieve relevant contexts or generate answers from multiple RAG corpora simultaneously using the AsyncRetrieveContexts and AskContexts APIs.
For more information, see RAG Cross Corpus Retrieval.
April 14, 2026
Feature
Anthropic's Claude Opus 4.7
Claude Opus 4.7
is available in Model Garden.
April 06, 2026
Feature
Metadata search for RAG Engine
Use schema-based metadata search in Vertex AI RAG Engine.
You can define a metadata schema for a corpus, attach metadata to files within
that corpus, and use this metadata to filter contexts during retrieval.
For more information, see
Filter with metadata search.
April 03, 2026
Feature
Gemma 4 26B A4B IT is available as an experimental launch in Model Garden. This is an open model built by Google DeepMind. Gemma 4 models are multimodal, handling text and image input and generating text output.
Gemma 4 26B A4B IT is available as a managed API in Model Garden. To learn more, see
Gemma 4 26B A4B IT.
Feature
Vertex AI RAG Engine Serverless mode
Vertex AI RAG Engine Serverless mode is now available in public
preview. Serverless
mode provides a fully managed database for storing RAG resources that abstracts
away database provisioning and scaling. You can seamlessly switch between
Serverless mode and Spanner mode, which provides dedicated, isolated database
instances.
For more information, see the following:
Deployment modes in Vertex AI RAG Engine
Serverless mode
Managing Spanner mode
Switching between modes
April 02, 2026
Feature
Veo 3.1 Lite
Veo 3.1 Lite is available in public
preview. This release
is our most cost-efficient Veo on Vertex AI model.
For more information, see 3.1 Lite
Generate
Announcement
Gemini 2.5 model retirement dates updated
The retirement dates for Gemini 2.5 Pro, Gemini 2.5 Flash-Lite,
and Gemini 2.5 Flash have been updated to October 16, 2026. For more information,
see Model versions and lifecycle.
March 25, 2026
Feature
Lyria 3
Lyria is available in public
preview. You can use
lyria-3-pro-preview to generate 184 seconds of audio, or
lyria-3-clip-preview to generate 30 seconds of audio.
For more information, see the following:
Lyria 3 Pro
Preview
Lyria 3 Clip Preview
March 24, 2026
Deprecated
Imagen generation GA endpoints deprecation
The following table describes image generation endpoints that are deprecated and
their replacements. We recommend updating your model endpoints before June 30,
2026, to avoid service disruption.
|
| Discontinued endpoints
| Recommended endpoint migration
| imagegeneration@002
| gemini-2.5-flash-image
| imagegeneration@003
| gemini-2.5-flash-image
| imagegeneration@004
| gemini-2.5-flash-image
| imagegeneration@005
| gemini-2.5-flash-image
| imagegeneration@006
| gemini-2.5-flash-image
| imagetext@001
| gemini-2.5-flash-image
| imagen-3.0-capability-001
| gemini-2.5-flash-image
| imagen-3.0-capability-002
| gemini-2.5-flash-image
| imagen-3.0-fast-generate-001
| gemini-2.5-flash-image
| imagen-3.0-generate-001
| gemini-2.5-flash-image
| imagen-3.0-generate-002
| gemini-2.5-flash-image
| imagen-4.0-fast-generate-001
| gemini-2.5-flash-image
| imagen-4.0-generate-001
| gemini-2.5-flash-image
| imagen-4.0-ultra-generate-001
| gemini-2.5-flash-image
Deprecated
Video generation GA endpoints deprecation
The following table describes video generation endpoints that are deprecated and
their replacements. We recommend updating your model endpoints before June 30,
2026, to avoid service disruption.
|
| Discontinued endpoints
| Recommended endpoint migration
| veo-3.0-generate-001
| veo-3.1-generate-001
| veo-3.0-fast-generate-001
| veo-3.1-fast-generate-001
| veo-2.0-generate-001
| veo-3.1-generate-001
March 12, 2026
Feature
Partner model evaluations
The Gen AI evaluation service supports evaluating partner models, such as Anthropic
and Llama models. For more information, see
Perform evaluation using the console.
March 03, 2026
Deprecated
Video generation preview endpoints deprecation
The following table describes video generation endpoints that are deprecated and
their replacements. We recommend updating your model endpoints before April 2,
2026, to avoid service disruption.
|
| Discontinued endpoints
| Recommended endpoint migration
| veo-3.0-generate-preview
| veo-3.0-generate-001
| veo-3.0-fast-generate-preview
| veo-3.0-fast-generate-preview
| veo-2.0-generate-preview
| veo-2.0-generate-001
| veo-2.0-generate-exp
| veo-2.0-generate-001
| veo-001-preview-0815
| veo-2.0-generate-001
| veo-001-preview
| veo-2.0-generate-001
| veo-3.1-generate-preview
| veo-3.1-generate-001
| veo-3.1-fast-generate-preview
| veo-3.1-fast-generate-001
Feature
Gemini 3.1 Flash-Lite
Gemini 3.1 Flash-Lite (gemini-3.1-flash-lite) is
available in public preview.
This release is our most cost-efficient Gemini model and is
optimized for low latency use cases for high-volume, cost-sensitive LLM traffic.
For more information, see
Gemini 3.1 Flash-Lite.
February 26, 2026
Feature
Gemini 3.1 Flash Image
Gemini 3.1 Flash Image (gemini-3.1-flash-image) is available
in public preview.
This release enables high-quality image generation with improved pricing and
latency. We recommend using Gemini 3.1 Flash Image when generating
images.
For more information, see
Gemini 3.1 Flash Image.
February 23, 2026
Deprecated
Anthropic's Claude 3 Haiku
Anthropic's Claude 3 Haiku is deprecated as of February 23, 2026 and will be
shut down on August 23, 2026. For more information, see
Partner model deprecations.
February 19, 2026
Feature
Gemini 3.1 Pro Preview
Gemini 3.1 Pro
is available in preview in Model Garden. Gemini 3.1 Pro is
our most advanced reasoning Gemini model, capable of solving complex
problems from different information sources, including text, audio, images,
video, PDFs, and even entire code repositories with its 1M token context
window.
February 17, 2026
Feature
Anthropic's Claude Sonnet 4.6
Claude Sonnet 4.6
is available in Model Garden.
Deprecated
Image generation preview endpoints deprecation
The following table describes image generation endpoints that are deprecated and
their replacements. We recommend updating your model endpoints before March 19,
2026, to avoid service disruption.
|
| Discontinued endpoints
| Recommended endpoint migration
| gemini-2.0-flash-image-generation-preview
| gemini-2.5-flash-image
| gemini-2.5-flash-image-generation-preview
| imagen-4.0-generate-001 or gemini-2.5-flash-image
| imagen-4.0-generate-preview-05-20
| imagen-4.0-generate-001 or gemini-2.5-flash-image
| imagen-4.0-generate-preview-06-06
| imagen-4.0-generate-001 or gemini-2.5-flash-image
| imagen-4.0-ultra-generate-preview-06-06
| imagen-4.0-generate-001 or gemini-2.5-flash-image
| imagen-4.0-fast-generate-preview-05-20
| imagen-4.0-generate-001 or gemini-2.5-flash-image
| imagen-product-recontext-preview-06-30
| gemini-2.5-flash-image
| imagen-2.0-edit-preview-0627
| gemini-2.5-flash-image
| virtual-try-on-preview-08-04
| virtual-try-on-001
| imagen-4.0-ingredients-preview
| gemini-2.5-flash-image
February 10, 2026
Feature
GLM 5 is available as an experimental launch in Model Garden. This model
is targeting complex systems engineering and long-horizon agentic tasks.
GLM 5 is available as a managed API in Model Garden. To learn more, see
GLM 5.
February 04, 2026
Feature
Anthropic's Claude Opus 4.6
Claude Opus 4.6
is available in Model Garden.
January 23, 2026
Feature
Virtual Try-On
Virtual Try-On is now generally available
(GA).
The new endpoint, virtual-try-on-001,
replaces the previous endpoint, virtual-try-on-preview-08-04. We
recommend changing to the new endpoint as soon as possible.
For more information, see
Generate Virtual Try-On Images.
January 22, 2026
Announcement
Codestral (25.01) and Mistral Large (24.11) are retired as of January 23, 2026.
January 20, 2026
Feature
GLM 4.7 GA is now available in Model Garden. This model
is designed for core or vibe coding, tool use, and complex reasoning.
GLM 4.7 is available as a managed API in Model Garden. To learn more, see
GLM 4.7.
January 13, 2026
Feature
Veo 3.1 reference-to-video update
Veo 3.1 Preview models now support the following features:
9:16 aspect ratio for reference-to-video.
Upsampling for videos generated at 1080p and 4k resolutions.
For more information, see the following:
Generate Veo videos from reference images
Veo on Vertex AI video generation API
January 06, 2026
Feature
GLM 4.7 is available as an experimental launch in Model Garden. This model
is designed for core or vibe coding, tool use, and complex reasoning.
GLM 4.7 is available as a managed API in Model Garden. To learn more, see
GLM 4.7.
January 05, 2026
Deprecated
Anthropic's Claude 3.5 Haiku
Anthropic's Claude 3.5 Haiku is deprecated as of January 5, 2026 and will be
shut down on July 5, 2026. For more information, see
Partner model deprecations.
December 18, 2025
Feature
The following models are available through Model Garden:
FunctionGemma
T5Gemma 2
Feature
Save and share prompts in Vertex AI Studio: The prompt sharing feature no longer needs to be enabled. You can share prompts without asking your administrator to first enable the prompt sharing feature. For more information, see Save and share prompts.
December 17, 2025
Feature
Cloud API Registry is available
in the Google Cloud console in
Preview. Use
Cloud API Registry in the Google Cloud console to view and manage the MCP
servers and tools your agent has access to.
Feature
Gemini 3 Flash
Gemini 3 Flash is now available in public preview. This model is designed to
tackle the most challenging agentic problems with strong coding and
state-of-the-art reasoning capabilities, and is our best model for complex
multimodal understanding.
For more information, see Gemini 3
Flash.
December 16, 2025
Change
Updated pricing for Vertex AI Agent Engine:
Pricing for Vertex AI Agent Engine Runtime was lowered.
On January 28, 2026, Sessions, Memory Bank, and Code Execution will begin
charging for usage.
For more information, see Pricing.
Announcement
Vertex AI Agent Engine
Vertex AI Agent Engine Sessions
and Memory Bank are now
Generally Available.
Change
Vertex AI Agent Engine
Vertex AI Agent Engine is now available in the following regions:
europe-west6 (Zurich)
europe-west8 (Milan)
asia-east2 (Hong Kong)
asia-northeast3 (Seoul)
asia-southeast2 (Jakarta)
northamerica-northeast2 (Toronto)
southamerica-east1 (São Paulo)
For more information, see Vertex AI Agent Builder locations.
Change
Virtual Try-On
Our Virtual Try-On model, virtual-try-on-preview-08-04, is
improved. Latency is significantly reduced and quality is improved for shoes,
body shape preservation, and product fidelity.
December 12, 2025
Feature
Gemini 2.5 Flash with Gemini Live API Native Audio
Gemini 2.5 Flash with Gemini Live API Native Audio (gemini-live-2.5-flash-native-audio) is Generally Available (GA).
This model features cutting-edge native audio functionality for
Gemini Live API, including enhanced voice quality and adaptability, Proactive Audio, and Affective Dialog.
December 10, 2025
Feature
DeepSeek-V3.2 is available in Model Garden.
DeepSeek-V3.2 is a state-of-the-art large language model from
DeepSeek.
DeepSeek-V3.2 is available as a managed API in Model Garden. To learn more, see
DeepSeek-V3.2.
December 09, 2025
Feature
The following models are available through Model Garden:
Ministral 3
Mistral Large 3
December 08, 2025
Feature
Veo 3.1 video extension
Veo 3.1 supports video extension in Preview.
For more information, see the following:
Extend Veo
videos
Veo video generation API
December 02, 2025
Feature
The following models are available through Model Garden:
DeepSeek-V3.2
DeepSeek-V3.2-Speciale
Feature
The Vertex AI Model Garden model co-hosting vLLM container is available to use with this sample notebook. You can use this container to serve multiple replicas of a model and serve multiple models with dynamic loading and unloading. This allows you to maximize resource utilization and serving efficiency, and flexibly adjust the models to serve.
November 24, 2025
Feature
Anthropic's Claude Opus 4.5
Claude Opus 4.5
is available in Model Garden.
November 17, 2025
Feature
Veo video generation
Veo 3.1 is Generally Available, and introduces the following models:
Veo
3.1
Veo 3.1
Fast
For more information, see the following:
Generate videos with Veo on Vertex AI
Generate Veo videos from text prompts
Generate Veo videos from an image
Generate Veo videos using first and last frames
Veo video generation API
Announcement
LearnLM in Gemini
The LearnLM model is no longer a separate offering or listing on AI Studio as
LearnLM capabilities have been integrated into the latest Gemini models (starting with Gemini 2.5).
Built in collaboration with experts in education,
LearnLM represents our
capabilities fine-tuned for learning informed by rigorous research. These
advancements and improvements are available directly in Gemini, enhancing
educational experiences and applications.
Pre-existing learnlm-2.0-flash-experimental projects will not remain functional
past December 3, 2025 unless an alternative model is manually selected—we
encourage developers to switch to the latest Gemini models and optimize their
prompts by reviewing our
LearnLM Partner Prompt Guide.
November 13, 2025
Feature
Kimi K2 Thinking is available in Model Garden. This model is
a thinking model that excels at complex problem-solving and deep reasoning.
Kimi K2 Thinking is available as a managed API in Model Garden. To learn more, see
Kimi K2 Thinking.
Feature
Updated Prompt Caching for Anthropic Claude Models
Prompt caching for Anthropic Claude models now supports a one-hour Time To Live (TTL).
For more information, see Prompt caching.
November 11, 2025
Deprecated
Anthropic's Claude 3.7 Sonnet
Anthropic's Claude 3.7 Sonnet is deprecated as of November 11, 2025 and will be
shut down on May 11, 2026. For more information, see
Partner model deprecations.
November 07, 2025
Feature
Vertex AI Agent Engine
The following features are now available in Preview:
Configure, manage, and view observability
features
such as sessions, traces, logs, and events for your agent in the Google Cloud console.
Use the
playground
to test and interact with your agent in the Google Cloud console.
Evaluate your agents using the
Gen AI evaluation service's GenAI Client in Vertex AI SDK.
Create and manage memory
revisions for Memory Bank.
Use Identity Access Management (IAM) to create an agent
identity to manage access and
authentication when using agents on Vertex AI Agent Engine Runtime.
The following features are now available in GA:
Express mode support for
Vertex AI Agent Engine Runtime.
Use the new free tier with Vertex AI Agent Engine Runtime. For more
information, see
Pricing.
November 04, 2025
Feature
MiniMax M2 is available in Model Garden. This model is
is built for end-to-end development workflows and has strong capabilities
in planning and executing complex tool-calling tasks. The model is
optimized to provide a balance of performance, cost, and inference speed.
MiniMax M2 is available as a managed API in Model Garden. To learn more, see
MiniMax M2.
October 23, 2025
Feature
The following models are available through Model Garden:
DeepSeek-OCR
Qwen3-VL
Earth AI
October 21, 2025
Security
On September 23, 2025, we discovered a technical issue in
the Vertex AI API that resulted in a limited amount of responses
being misrouted between recipients for certain third-party models
when using streaming requests. This issue is now resolved.
Google models, e.g. Gemini, were not impacted.
Some internal proxies did not properly handle HTTP requests that
have an Expect: 100-continue header, resulting in
a desynchronization in a streaming response connection, where
a response intended for one request was instead delivered as
the response for a subsequent request.
For more information, see
Security bulletins.
October 16, 2025
Feature
Mistral's Codestral 2
You can use Mistral's
Codestral 2
in Model Garden.
Feature
vLLM TPU
vLLM TPU, a
highly-efficient serving framework for large language models (LLM) that's
optimized for Cloud TPU hardware, is available through
Model Garden.
October 15, 2025
Feature
Anthropic's Claude Haiku 4.5
You can use Anthropic's
Claude Haiku 4.5
in Model Garden.
Feature
Veo video generation
Veo 3.1 is available in Preview, and introduces the following models:
Veo
3.1 preview
Veo 3.1
Fast preview.
For more information, see the following:
Generate videos with Veo on Vertex AI
Generate Veo videos from text prompts
Generate Veo videos from an image
Generate Veo videos using first and last frames
Direct Veo using a reference image
Veo video generation API
Feature
Veo video generation
Veo 2 supports adding and removing objects from videos in Preview.
For more information about Veo 2, see Veo 2
Preview
For more information about adding and removing objects, see the following:
Insert objects into Veo videos
Remove objects from Veo videos
Veo video generation API
October 14, 2025
Deprecated
Imagen subject and style fine-tuning
Imagen subject model and style model tuning will be removed on
December 31, 2025. We recommend that you use
Gemini 2.5 Flash Image, which supports most use cases that require
fine-tuning. For more information, see Edit images with
Gemini.
Deprecated
Imagen 4 preview models
The following Imagen 4 preview models will be removed on
November 30, 2025:
imagen-4.0-generate-preview-06-06,
imagen-4.0-ultra-generate-preview-06-06, and
imagen-4.0-fast-generate-preview-06-06. To avoid service
disruption, migrate all workflows that use Imagen 4 preview models before
November 30, 2025, 2025, to the following Imagen 4 Generally
Available models: imagen-4.0-generate-001,
imagen-4.0-ultra-generate-001,
imagen-4.0-fast-generate-001.
October 09, 2025
Change
Imagen
Imagen's virtual try-on model, virtual-try-on-preview-08-04
was updated on September 30, 2025, to more accurately preserve the person's
body shape and preserve the garment's identity.
October 07, 2025
Feature
The following Qwen models are available in Model Garden:
Qwen-Image
Qwen-Image-Edit
Qwen-Image-Edit-2509
Announcement
The Computer Use tool (gemini-2.5-computer-use-preview-10-2025) is now available in Preview. The Computer Use model and tool lets you enable your applications to interact with and automate tasks in the browser. With the Computer Use model and tool, you can build agents that can:
Automate repetitive data entry or form filling on websites.
Navigate websites to gather information.
Assist users by performing sequences of actions in web applications.
October 06, 2025
Change
Updated pricing for Vertex AI Agent Engine: Starting on November 6, 2025, Vertex AI Agent Engine Runtime will start charging for runtime usage for the following regions:
asia-southeast1 (Singapore)
australia-southeast2 (Melbourne)
europe-west2 (London)
europe-west3 (Frankfurt)
europe-west4 (Netherlands)
For more details, see Pricing for Vertex AI Agent Engine.
Feature
Access Transparency for Vertex AI Agent Engine: Access Transparency is now available for Vertex AI Agent Engine. For more information, see the overview for Enterprise security.
October 03, 2025
Feature
Prompt management
Vertex AI offers tooling to help manage prompts and prompt versions. In addition to the prompt management capabilities in Vertex AI Studio, prompts can be stored and versioned using the Vertex AI SDK.
For more information, see the Prompt management API reference.
October 02, 2025
Announcement
Gemini 2.5 Flash Image (gemini-2.5-flash-image) is now generally available. This GA release adds support for aspect ratio controls, image-only response modality, regional endpoints, support for batch predictions, image generation from multiple reference images, and improved multi-turn image editing.
See Gemini 2.5 Flash Image for more information.
Feature
Google Gen AI SDK in C# Preview
Preview: The Google Gen AI SDK is available in C#. See googleapis/dotnet-genai.
This release includes support for GenerateContentAsync, GenerateContentStreamAsync, GenerateImagesAsync, and three Live APIs, which includes SendClientContentAsync, SendRealtimeInputAsync, and SendToolResponseAsync.
September 30, 2025
Feature
DeepSeek-V3.2-Exp is available through Model Garden.
September 25, 2025
Announcement
New preview models for Gemini 2.5 Flash and 2.5 Flash-Lite are now available. These models are available at the following versioned endpoints:
gemini-2.5-flash-preview-09-2025
gemini-2.5-flash-lite-preview-09-2025
September 24, 2025
Deprecated
Access to Gemini's 1.5 models has been discontinued. For more information, see our Model versions page.
September 23, 2025
Announcement
Gemini 2.5 Flash with Live API Native Audio Preview
Gemini 2.5 Flash with Live API Native Audio (gemini-live-2.5-flash-preview-native-audio-09-2025) is available in Preview. A single, unified model processes audio input and generates audio output directly, eliminating separate text-to-speech/speech-to-text conversions. This results in-low latency, high-quality, and incredibly human-like conversations. New features and capabilities include:
Improved Barge-in: Interrupt Gemini more naturally and reliably, even in loud and noisy environments.
Robust Function Calling: We've improved the triggering rate, allowing Gemini to successfully execute the functions you define with greater precision.
Accurate Transcription: The accuracy of audio-to-text transcription has been significantly enhanced.
Seamless Multilingual Support: Speak to Gemini in multiple languages, and it will effortlessly switch between them without any pre-configuration. Language is no longer a barrier!
Enhanced Audio Quality: Experience a dramatically improved audio quality that truly feels like speaking with a person.
Proactive Audio: Define Gemini's expertise and set conditions for when it should respond. Gemini can act as a "silent listener," only chiming in when the conversation touches upon its designated area of expertise.
Affective Dialog: Gemini can adapt and adjust its generated voice to match the emotional tone of the speaker, creating more empathetic and natural interactions.
Watch our comprehensive demo to see these features in action, including seamless language switching, expert mode, emotionally aware responses, memory recall, and interactive screen sharing for engineering tasks – all demonstrated directly within Vertex AI Studio without writing a single line of code!
September 22, 2025
Feature
DeepSeek-V3.1-Terminus is available through Model Garden.
September 18, 2025
Change
Grounding with Google Maps
Grounding with Google Maps has implemented the following changes:
Removed the following fields from the API response:
grounding_chunk.maps.text
grounding_chunk.maps.place_answer_sources.review_snippets.author_attribution
grounding_chunk.maps.place_answer_sources.flag_content_uri
grounding_chunk.maps.place_answer_sources.review_snippets.flag_content_uri
The widget context token is only returned when the optional widget_token_enable input flag is set.
To learn more, see Grounding with Google Maps.
September 15, 2025
Change
Imagen
We improved Imagen's virtual try-on model, virtual-try-on-preview-08-04, so that it is better at preserving the person's body shape and preserving the garment product's identity.
September 10, 2025
Breaking
Vertex AI Agent Engine
In version v1.112.0 of the Vertex AI SDK for Python, the agent_engines module has been refactored to a client-based design. For information about updating your existing code to the new design, see the Migration guide.
Feature
Vertex AI Agent Engine
Agent Engine now supports the following features:
Agent Engine Code Execution, now in Preview, lets your agent run code in an isolated sandbox environment. For more information, see Code Execution.
You can now develop, deploy, and use agents that support the Agent-to-Agent (A2A) protocol on Agent Engine. For more information, see Develop an Agent2Agent agent.
Agent Engine now supports bidirectional streaming. For more information, see Bidirectional streaming.
The Agent Engine page in the Cloud Console UI now has a new Memory Bank tab for displaying and managing memories.
September 09, 2025
Feature
EmbeddingGemma and DeepSeek-V3.1 models are available through Model Garden.
Feature
AI Singapore's SEA-LION V4 models are available through Model Garden. They are open models for Southeast Asian languages, built by leveraging Vertex Model Development Service for enhanced training efficiency and model accuracy.
September 08, 2025
Feature
Veo video generation
Veo 3 support for short-duration videos is generally available. You can use Veo 3 to create 4, 6, or 8 second videos. For more information, see the following:
Generate videos with Veo on Vertex AI from text prompts
Generate videos with Veo on Vertex AI from an image
Veo on Vertex AI video generation API
September 03, 2025
Change
Vertex AI RAG Engine: Managed Database (Spanner)
Customers will be charged for the use of a Google-managed Spanner instance that's provisioned in a Google tenant project, using standard Spanner SKUs.
For more information, see Vertex AI RAG Engine billing.
August 26, 2025
Announcement
Gemini 2.5 Flash Image Preview
Gemini 2.5 Flash Image (gemini-2.5-flash-image-preview) is available in Preview. Gemini 2.5 Flash Image Preview supports additional image generation and editing features such as image generation from multiple reference images and improved multi-turn image editing.
Feature
Vertex AI model tuning and Gen AI evaluation service
Vertex AI model tuning now supports integration with the Gen AI evaluation service in Preview. You can automatically run evaluations on your tuned models and intermediate checkpoints. For more information, see Create a tuning job.
August 21, 2025
Feature
Vertex AI Agent Engine
Agent Engine now supports the following enterprise security features:
You can now deploy your agents in a private VPC environment, configuring a Private Service Connect interface, to ensure data privacy and meet security and compliance requirements. For more information, see Configure Private Service Connect interface.
You can now use your own customer-managed encryption keys (CMEK) to protect data at rest.
You can now specify customized resource controls, such as the minimum and maximum number of application instances, resource limits for each container, and concurrency for each container.
As a part of Vertex AI Platform, Vertex AI Agent Engine now supports HIPAA workloads.
For more information, see Agent Engine overview.
August 14, 2025
Announcement
Imagen
Imagen 4 is Generally Available.
Imagen 4 introduces the following models:
Imagen 4 Generate
Imagen 4 Fast Generate
Imagen 4 Ultra Generate
For more information, see Generate images using text prompts and Image generation API.
Feature
Gemma 3 270M, Wan 2.2 and Wan 2.1 models are available through Model Garden.
August 13, 2025
Feature
Qwen3 Coder and Qwen3 235B are available as Model as a Service (MaaS) models in Model Garden.
Feature
OpenAI's gpt-oss-120b and gpt-oss-20b are available as Model as a Service (MaaS) models in Model Garden.
August 08, 2025
Feature
Gemini 2.5 Flash-Lite and Gemini 2.5 Pro now support supervised fine-tuning. For more information, see About supervised fine-tuning for Gemini models.
August 07, 2025
Feature
Vertex AI Agent Engine
You can use your own custom service account for agent identity to manage permissions and access according to your organization's security policies.
Feature
Model tuning
You can now perform supervised fine-tuning on open models such as Llama 3.1. For more information, see Tune an open model.
Feature
Vertex AI prompt optimizer
The Vertex AI prompt optimizer is now generally available. For more information, see Optimize prompts.
We now offer a zero-shot prompt optimizer.
August 06, 2025
Feature
OpenAI's gpt-oss models are available through Model Garden.
Feature
Imagen
Virtual try-on lets you generate virtual try-on images from an image of a
person and product photos that you provide, and is available in Preview. For more information, see Generate Virtual Try-On Images and Virtual Try-On API.
This release note is incorrect; see entry for October 9, 2025.
July 29, 2025
Announcement
Veo video generation Veo 3 and Veo 3 Fast are now generally available. For more information, see Generate videos using text prompts.
July 23, 2025
Change
Grounding with Google Maps is available in all regions (except for the EEA) as a Preview (Pre-GA) feature.
July 22, 2025
Announcement
Gemini 2.5 Flash-Lite is now generally available and accessible using the API and Vertex AI Studio. This GA release includes support for explicit caching and batch prediction, as well as expanded region support.
See Gemini 2.5 Flash-Lite for more information.
July 17, 2025
Announcement
Veo 3 preview models now support upscaling for 1080p resolution using the new resolution parameter. For more information, see Veo on Vertex AI.
July 16, 2025
Feature
Added Gemma 3 fine-tuning notebook using Axolotl docker with support for 1b, 4b, 12b, and 27b variants.
July 14, 2025
Feature
Multimodal MedGemma 27B IT, MedSigLIP, and T5Gemma models are available through Model Garden.
July 08, 2025
Feature
Vertex AI Agent Engine
Vertex AI Agent Engine Memory Bank is now available in Preview. Memory Bank lets you dynamically generate long-term memories based on users' conversations with your agent.
July 03, 2025
Feature
Vertex AI Agent Garden
Vertex AI Agent Garden now supports filtering by tags.
June 27, 2025
Feature
Gemma 3n models are now available through Model Garden.
Feature
Multimodal datasets are now available in preview. For more information, see Multimodal datasets.
June 24, 2025
Deprecated
Starting on June 24, 2025, Imagen versions 1 and 2, image captioning, and visual question answering are deprecated.
On September 24, 2025, the following features and models will be removed:
image captioning
visual question answering
Imagen 1 model imagegeneration@002
Imagen 2 models imagegeneration@005 and imagegeneration@006
For more information, see Migrate to Imagen 3.
June 23, 2025
Announcement
Veo 2 support for advanced video controls is Generally Available. In addition to a providing a first frame of a video, you can specify the last frame of a video or a video to extend in length. For more information, see Veo on Vertex AI API.
June 17, 2025
Change
Updated pricing for Gemini 2.5 Flash GA: The price for Gemini 2.5 Flash in GA will be adjusted to reflect its quality and unified output token pricing. This includes lower prices for thinking output, higher prices for non-thinking output. These pricing changes will take effect on the new GA endpoint as shared above. Preview pricing will only continue on existing preview endpoints for 30 days post-GA on July 15, 2025.
Change
Provisioned Throughput (PT): Once a model is GA, all new PT purchases will be for GA endpoints only. If you've purchased PT for a specific preview version, it will still work for that specific preview. However, you must migrate the existing PT to the GA endpoint or purchase new PT for the GA endpoint by July 15, 2025.
Announcement
Gemini 2.5 Flash-Lite is now available as a preview offering in both the API and Vertex AI Studio.
See Gemini 2.5 Flash-Lite for more information.
Announcement
Live API is now available as a private general availability offering in the API and Vertex AI Studio. Reach out to your Google account team representative to request access.
See Live API for more information.
Announcement
Gemini 2.5 Flash and Gemini 2.5 Pro are now generally available and accessible using the API and Vertex AI Studio.
See Gemini 2.5 Flash and Gemini 2.5 Pro for more information.
Deprecated
Preview endpoint availability and removal: All existing Gemini 2.5 Flash and Pro preview endpoints (listed below) will continue to be available with their current preview pricing until July 15, 2025. After this date, these preview endpoints will be shut down.
gemini-2.5-flash-preview-04-17
gemini-2.5-flash-preview-05-20
gemini-2.5-pro-preview-03-25
gemini-2.5-pro-preview-05-06
gemini-2.5-pro-preview-06-05
Change
Updated preview endpoints: Effective June 19, 2025, gemini-2.5-flash-preview-04-17 endpoint will serve the Gemini 2.5 Flash model version released on 05-20, which has been promoted to GA. Similarly, the gemini-2.5-pro-preview-05-06 and 03-25 endpoints will serve the Gemini 2.5 Pro model version released on 06-05, also promoted to GA. This update ensures continuity during your transition.
June 16, 2025
Announcement
The DeepSeek API service on Vertex AI is in Preview. For more information, see the DeepSeek model card in Model Garden.
June 11, 2025
Change
Imagen 4's public preview models are updated to the following:
imagen-4.0-generate-preview-06-06
imagen-4.0-fast-generate-preview-06-06
imagen-4.0-ultra-generate-preview-06-06
For more information about each model, see Preview Imagen models.
To avoid service interruption, migrate from imagen-4.0-ultra-generate-exp-05-20 and imagen-4.0-generate-preview-05-20 before 2025-07-07.
June 09, 2025
Change
Gemini API
The logprobs and response_logprobs parameters for the Gemini API are now generally available. For more information, see Generate content with Gemini API.
June 05, 2025
Feature
Gemini 2.5 Pro's public preview version has been updated to gemini-2.5-pro-preview-06-05 and includes expanded support for thinking. This model version is available in the API and Vertex AI Studio.
See Gemini 2.5 Pro for model details.
June 03, 2025
Announcement
In Model Garden, the following fine tuning features have been added:
Gemma 3 UI fine-tuning using PEFT docker.
Qwen 2.5 fine-tuning notebook using PEFT docker.
Qwen 3 fine-tuning notebook using Axolotl docker.
lm-evaluation-harness as an evaluation service in the Llama 3.3, Llama 3.1, Gemma 3 and Gemma 2 fine-tuning notebooks.
Announcement
Model Garden now includes DeepSeek-R1-0528 variants.
May 23, 2025
Announcement
Mistral OCR is an Optical Character Recognition API for document understanding. It is GA on Vertex AI. For more information, see the Mistral OCR model card in Model Garden.
May 22, 2025
Announcement
Anthropic's Claude Opus 4 and Claude Sonnet 4 are GA on Vertex AI and support Provision Throughput. For more information, see the Claude Opus 4 or Claude Sonnet 4 model card in Model Garden.
May 20, 2025
Feature
Vertex AI Agent Engine
The following features are now available in Preview:
Console support for managing deployed agents
Sessions support for Agent Development Kit agents
Feature
Audio-to-audio support for Gemini 2.5 Flash with Live API is now available as a private preview. Users must be allowlisted to use this new feature.
The model is available in the API and Vertex AI Studio.
See Live API for details.
Change
Gemini 2.5 Flash's public preview version has been updated to gemini-2.5-flash-preview-5-20.
See Gemini 2.5 Flash for model details.
The model is available in the API and Vertex AI Studio.
Announcement
New stable text embeddings models are now generally available:
gemini-embedding-001
text-embedding-005
For more information, see Get text embeddings.
Feature
Thought summaries are now available as an experimental feature for Gemini 2.5 Pro and 2.5 Flash.
For details, see Thinking.
The model is available in the API and Vertex AI Studio.
Feature
Imagen 4
Imagen 4 offers two Preview models: Imagen 4 Generate Preview 05-20, and Imagen 4 Ultra Generate Experimental 05-20.
For more information, see
Generate images using text prompts and the
Generate images API.
The model is available in the API and Vertex AI Studio.
Announcement
Lyria 2, our latest music generation model, is now generally available.
See our music generation prompt guide and our user guide for more information.
The model is available in the API and Vertex AI Studio.
Announcement
MedGemma models are available in Model Garden.
Feature
Veo 3
Veo 3 is available in Preview for allowlisted accounts.
For more information about Veo 3, see Veo | AI Video Generator and Veo on Vertex AI API.
The model is available in the API and Vertex AI Studio.
May 14, 2025
Deprecated
MedLM is deprecated. Access to MedLM will no longer be available on or after September 29, 2025.
May 07, 2025
Feature
Gemini 2.0 Flash with image generation (gemini-2.0-flash-preview-image-generation) is now available as a public preview offering.
For more information, see Generate images with Gemini.
Fixed
Seed parameter is now in GA and supports Gemini 2.5 model family.
May 05, 2025
Change
Grounding
The following grounding features are generally available:
Grounding on your data using Vertex AI Search
Grounding with Elasticsearch
May 02, 2025
Announcement
The global endpoint is generally available (GA). For details, see Global endpoint.
April 30, 2025
Change
Additional materials are available for deploying a model in Model Garden by using the Python SDK, gcloud CLI, or API, which are available in Preview:
Developer blog: Introducing the new Vertex AI Model Garden CLI and SDK
Deploy open models by using the SDK tutorial notebook
Get started with Vertex AI Model Garden SDK notebook
Feature
Llama 4 Maverick and Scout models are available in Model Garden with Model-as-a-Service API Service and self-hosted deployments.
HiDream-I1, Llama Guard 4, Llama Prompt Guard 2, and Qwen3 are available in Model Garden.
April 29, 2025
Announcement
Gemini 1.5 Pro and Gemini 1.5 Flash models are not available in projects that have no prior usage of these models, including new projects. For details, see
Model versions and lifecycle.
April 17, 2025
Announcement
Gemini 2.5 Flash with thinking and other well-rounded capabilities is now available in Preview.
April 10, 2025
Announcement
Managed APIs for Llama 4 Maverick and Scout are in Preview on Vertex AI. For more information, see the Llama 4 model card.
April 09, 2025
Feature
Vertex AI Agent Engine
The following features are now available for Vertex AI Agent Engine in Preview:
Agent Development Kit integration
Example Store
LlamaIndex Query Pipeline integration
The following features are now generally available for Vertex AI Agent Engine:
Agent monitoring
Feature
Gemini Live API is now available as a public preview offering and has been updated with the following features:
Support for responses in 8 voices and 31 languages using Chirp 3
Updated UI support in Vertex AI Studio
Expanded conversation session window
Ability to extend conversation sessions
Support to share your current screen with Gemini during conversations
Transcription support for audio in and audio out
Support to change or update the system instructions mid-session
For more information, see Gemini 2.0 Flash Live API.
Feature
Agent Development Kit (ADK) is now available in Preview. For more information, see Agent Development Kit.
Feature
Gemini 2.5 Pro is now available as a public preview offering.
For more information, see Gemini 2.5 Pro.
Feature
Agent Garden is now available in Preview. For more information, see Vertex AI Agent Builder overview or go directly to Agent Garden in the Cloud Console.
Change
Vertex AI Agent Builder now refers to a suite of features for building and deploying AI agents in Vertex AI. For more information see, Vertex AI Agent Builder overview.
The original Vertex AI Agent Builder product has been renamed AI Applications. The product functionality and endpoints remain the same. For more information, see What is AI Applications?.
Feature
Grounding: Web Grounding for Enterprise is now Generally available. For more information, see Web Grounding for Enterprise.
Feature
Grounding: Grounding with Google Maps is now available as a Public Experimental feature. For more information, see Grounding with Google Maps.
March 25, 2025
Feature
DeepSeek-V3-0324, TxGemma and Sesame CSM are now available in Model Garden.
DeepSeek-R1, V3 and V3-0324 can be deployed with H200 GPUs and improved vLLM support.
You can deploy a model in Model Garden by using the Python SDK, gcloud CLI, or API, which are available in Preview. You can get started with the "Equivalent code" in the deploy panel in the Model Garden console.
March 20, 2025
Announcement
Anthropic's Claude Sonnet 3.7 is GA on Vertex AI and supports Provision Throughput. To learn more, view the Claude Sonnet 3.7 model card in Model Garden.
March 17, 2025
Announcement
Mistral Small 3.1 (25.03) feature multimodal capabilities and a context of up to 128,000 tokens. For more information, see the Mistral Small 3.1 (25.03) model card in Model Garden.
March 14, 2025
Feature
Judge model evaluation and customization tools are now available in Preview for the Gen AI evaluation service in Vertex AI.
March 13, 2025
Announcement
Context caching for Gemini on Vertex AI is generally available (GA).
March 12, 2025
Change
Model Garden fine tuning updates:
Added a workbench-based notebook for Llama 3.1 finetuning.
Updated Llama 3.1 and Gemma 2 UI fine-tuning with the updated PEFT docker.
Feature
Gemma 3 and ShieldGemma 2 are now available in Model Garden.
CogVideoX-2b is now available in Model Garden.
March 11, 2025
Change
Gemini 2.0 Flash Tuning
Gemini 2.0 Flash fine-tuning is now generally available (GA).
Added support for tuning function calling.
March 04, 2025
Announcement
Vertex AI Agent Engine
Vertex AI Agent Engine is now generally available (GA).
Billing for Vertex AI Agent Engine starts on March 4, 2025. We recommend that you delete unused resources to avoid incurring unwanted costs. For more information, see Pricing.
Change
LangChain on Vertex AI has been renamed to Vertex AI Agent Engine.
February 25, 2025
Feature
Gemini 2.0 Flash-Lite is now generally available
Gemini 2.0 Flash-Lite is now generally available. For more information, see Gemini 2.0.
February 24, 2025
Announcement
Anthropic's Claude Sonnet 3.7 is in Preview on Vertex AI. To learn more, view the Claude Sonnet 3.7 model card in Model Garden.
February 21, 2025
Change
PEFT Docker updates
Added support for evaluation metrics like perplexity, bleu, google_bleu, rouge1, rouge2, rougeL, rougeLSum.
Uses the best checkpoint and loads the model based on the best eval metrics.
Run training and eval only for data which is less than or equal to the max_seq_length.
Use gcloud storage rsync instead of csfuse to save a checkpoint.
Fine tuning updates
You can select a service account when you click Fine-tune for a model, such as Llama 3.1.
Added a PEFT based LLM finetuning tutorial notebook.
Added a Axolotl based LLM finetuning notebook.
Updated Llama 3.1 and Gemma 2 fine-tuning notebooks with the updated PEFT Docker container.
Model updates
Updated the PaliGemma model card by supporting PaliGemma 2 mix models, and segmentation functionality to Paligemma 1 models.
Updated the LLaVa model card by supporting LLaVA Next models and adding vLLM to the notebook.
February 12, 2025
Feature
Deepseek-V3 and Deepseek-R1 have been added to Model Garden in Preview:
DeepSeek-V3 (671B) is a powerful Mixture-of-Experts (MoE) language model with 671B total parameters with 37B activated for each token.
DeepSeek-R1 (671B) is one of the first-generation reasoning models introduced by DeepSeek and offers performance comparable to OpenAI-o1 across math, code, and reasoning tasks.
You can use a notebook to deploy these models.
February 11, 2025
Announcement
The Llama 3.3 70B model that is managed on Vertex AI is now in Preview.
February 07, 2025
Feature
deepseek-ai/deepseek-r1 and microsoft/Phi-4 models were added to Model Garden.
Change
The following advanced LLM inference optimization techniques are available in Model Garden in Preview:
Prefix caching reuses computations from previously generated text, eliminating redundant processing. It reduces time-to-first-token for requests with common prompt prefixes. Prefix caching is available for the following models:
vLLM: Llama 3.1 (8b, 70b), Llama 3.3 (70b)
Hex-LLM: Llama 2 (7b, 13b), Llama 3 (8b), Llama 3.1 (8b, 70b), Llama 3.2 (1b, 3b), Llama Guard (1b, 8b), CodeLlama (7b, 13b), Gemma (2b, 7b), CodeGemma (2b, 7b), Mistral-7B (v0.2, v0.3), Mixtral-8x7B (v0.1)
Speculative decoding is an effective optimization technique to reduce generation time-per-output-token latency. For more information, see the Model Garden advanced features notebook.
February 05, 2025
Feature
Gemini 2.0 Flash general availability for text-only output
Gemini 2.0 Flash is now generally available for text-only outputs. Multimodal outputs are still available only as a private preview. For more information, see Gemini 2.0.
Feature
New Gemini 2.0 Pro and Gemini 2.0 Flash-Lite models available to users
Two new models in the Gemini 2.0 family are now available to users:
Gemini 2.0 Pro: Our strongest model for coding and world knowledge, featuring a 2M long context window. Gemini 2.0 Pro is available as an experimental model in Vertex AI.
Gemini 2.0 Flash-Lite: Our fastest and most cost efficient Flash model. Gemini 2.0 Flash-Lite is available as a Preview model in Vertex AI.
For more information, see Gemini 2.0
January 31, 2025
Feature
You can now monitor usage, throughput, and latency and troubleshoot 429 errors on Vertex AI foundation models, like Google Gemini and Anthropic Claude, by using a predefined dashboard. After querying a model from the Vertex AI Model Garden, you can find the name of the model you queried in the Vertex AI Dashboard page under the "Model observability" heading.
To customize the dashboard and explore relevant metrics in Cloud Monitoring, click Show All Metrics. For information about using dashboards in Cloud Monitoring, see View and customize Google Cloud dashboards.
January 30, 2025
Deprecated
Mistral Large (24.07) and Codestral (24.05) that are offered as a Model as a Service (MaaS) models in Model Garden are deprecated. For details, see Generative AI on Vertex AI deprecations.
January 29, 2025
Feature
New Imagen 3 image generation model available to users
A newer improved Imagen 3 image generation model is now available to all users:
imagen-3.0-generate-002
This image generation model supports the following additional features:
Prompt enhancement - The LLM-based prompt rewriter tool adds additional details and descriptive language to the prompt you provide, generally resulting in higher quality generated images. This feature is configurable and is enabled by default.
For more information, see Imagen on Vertex AI model versions and lifecycle and Generate images using text prompts.
January 22, 2025
Announcement
LangChain on Vertex AI
Billing for LangChain on Vertex AI will start on March 4, 2025.
The pricing structure is based on vCPU hours and GiB hours used. This means that you will be charged for both the compute (vCPU) and memory resources consumed by your LangChain on Vertex AI workloads.
You can review the pricing details in the table below.
|
| Product
| SKU ID
| Price
| ReasoningEngine vCPU
| 8A55-0B95-B7DC
| $0.0994/vCPU-Hr
| ReasoningEngine Memory
| 0B45-6103-6EC1
| $0.0105/GiB-Hr
January 21, 2025
Deprecated
Anthropic's Claude 3 Sonnet that is offered as a Model as a Service (MaaS) model in Model Garden is deprecated. For details, see Generative AI on Vertex AI deprecations.
January 17, 2025
Feature
Agent evaluation using the Gen AI evaluation service is available in Preview.
December 20, 2024
Change
RAG Engine is generally available (GA).
The supported models include the following:
Google Gemini
Google embedding and OSS E5 embedding models
Model Garden self-deployed OSS LLMs
Model as a service (MaaS) Llama models
The supported features include the following:
Data connectors: Google Cloud Storage, Google Drive, Slack, Jira, and SharePoint
Document types: Google Workspace documents, HTML, JSON, Markdown, PDF, and text files
Transformations: fixed-size chunking and chunk overlap
Vector databases: Vertex AI Vector Search and Pinecone
December 18, 2024
Feature
Hex-LLM: High-Efficiency Large Language Model Serving is available in General Availability (GA).
This launch adds support for the following models:
Llama 3.1
Llama 3.2
Phi-3
Qwen2 and Qwen2.5
Additional supported features:
Multi-host serving.
Disaggregated serving (experimental).
Prefix caching.
AWQ quantization.
December 17, 2024
Feature
You can copy tuned Gemini 1.5 Pro 002 and Gemini 1.5 Flash 002 adapter models across projects. For details, see Copy a model in Vertex AI Model Registry.
December 11, 2024
Feature
The Gemini 2.0 Flash (gemini-2.0-flash-exp) model is Generally available for grounded answer generation with RAG. This model is tuned to address context-based question and answering tasks. For more information, see Ground responses for Gemini models.
December 10, 2024
Feature
Imagen 3 image generation models Generally Available to all users
Imagen 3 image generation models are now available to all users without requiring prior approval. These include the following image generation models:
imagen-3.0-generate-001
imagen-3.0-fast-generate-001 (low latency model)
Prior image generation models (imagegeneration@006, imagegeneration@005, imagegeneration@002) still require approval to use.
For more information, see Imagen on Vertex AI model versions and lifecycle and Generate images using text prompts.
Feature
Imagen 3 Customization model Generally Available to approved users
Imagen 3 Customization model is now available to approved users. This includes the following model:
imagen-3.0-capability
Imagen 3 Customization lets you guide image generation by providing reference images (few-shot learning). Imagen 3 Customization lets you customize generated images for the following feature categories:
Subject Customization (product, person, and animal companion)
Style Customization
Controlled Customization (canny edge and scribble)
Instruct Customization (Style transfer)
Feature
Imagen 3 editing model Generally Available to approved users
The Imagen 3 Editing model is now available to approved users. This includes the following model:
imagen-3.0-capability
This model offers the following additional features:
Inpainting - Add or remove content from a masked area of an image
Outpainting - Expand a masked area of an image
Product image editing - Identify and maintain a primary product while changing the background or product position
For more information, see Model versions.
December 06, 2024
Security
A vulnerability was discovered in the Vertex AI API serving Gemini multimodal requests, allowing bypass of VPC Service Controls. For details, see the Security bulletins page.
November 21, 2024
Feature
The Gen AI evaluation service can now help you evaluate your translation models using MetricX, COMET, and BLEU metrics.
To learn more about evaluating your translation models, see Evaluate translation models.
Announcement
Mistral Large (24.11) is Generally Available on Vertex AI as a managed model. To learn more, view the Mistral Large (24.11) model card in Model Garden.
November 08, 2024
Feature
Batch predictions for Llama models on Vertex AI (MaaS) is available in Preview.
Feature
Batch prediction support for Gemini
Batch prediction is available for Gemini in General Availability (GA). Available Gemini models include Gemini 1.0 Pro, Gemini 1.5 Pro, and Gemini 1.5 Flash. To get started with batch prediction, see Get batch predictions for Gemini.
November 05, 2024
Change
We are extending the availability of Gemini 1.0 Pro 001 and Gemini 1.0 Pro Vision 001 from February 15, 2025 to April 9, 2025. For details, see the Deprecations.
November 04, 2024
Announcement
The Anthropic Claude Haiku 3.5 is Generally Available on Vertex AI. To learn more, view the Claude Haiku 3.5 model card in Model Garden.
Change
The translation LLM now supports Polish, Turkish, Indonesian, Dutch, Vietnamese, Thai and Czech. For the full list of supported languages, see the Translate text page.
October 28, 2024
Feature
The Whisper large v3 and Whisper large v3 turbo models have been added to Model Garden.
Feature
You can now fine-tune the following models from the Cloud console:
Gemma 2
Llama 3.1
Mistral
Mixtral
Change
Updated the fine-tuning notebooks for Gemma 2, Llama 3.1, Mistral, and Mixtral with the following enhancements:
The notebooks use an updated high-performance container for single host multi-GPU LoRA fine-tuning.
Better throughput and GPU utilization with well-tested max-sequence-lengths.
Support for input token masking.
No out of memory (OOM) error during fine-tuning.
Added a custom dataset example that uses a template and format validation.
Support for a default accelerator pool with quota checks.
Improved documentation.
October 22, 2024
Announcement
The Anthropic Claude Sonnet 3.5 v2 is Generally Available. To learn more, view the Claude Sonnet 3.5 v2 model card in Model Garden.
October 18, 2024
Announcement
The Llama 3.1 405B model that is managed on Vertex AI is now Generally Available.
October 09, 2024
Feature
The Vertex AI Gemini API SDK supports tokenization capabilities for local token counting and computation. This is a streamlined way to compute tokens locally, ensuring compatibility across different Gemini models and their tokenizers. Supported models include gemini-1.5-flash and gemini-1.5-pro . To learn more, see Count tokens.
October 04, 2024
Change
Added dynamic LoRA serving for Llama 3.1 and Stable Diffusion XL.
Feature
You can deploy Hugging Face models on Google Cloud that have text embedding inference enabled or pytorch inference
enabled. For more information, see the Hugging Face model deployment in the console.
Feature
Prompt Guard and Flux were added to Model Garden.
Change
Added multiple deployment settings (with A100-80G and H100) and sample requests for some popular models, including Llama 3.1, Gemma 2, and Mixtral.
Feature
The AI assistant in Vertex AI Studio can help you refine and generate prompts. This feature is in Preview. To learn more, see Use AI-powered prompt writing tools.
October 01, 2024
Feature
Grounding: Dynamic retrieval for grounded results (GA)
Dynamic retrieval lets you choose when to turn off grounding with Google Search. This is useful when a prompt doesn't require an answer grounded in Google Search, and the supported models can provide an answer based on their knowledge without grounding. Dynamic retrieval helps you manage latency, quality, and cost more effectively.
This feature is Generally Available. For more information, see Dynamic retrieval.
September 30, 2024
Feature
Prompt templates let you to test how different prompt formats perform with different sets of prompt data. This feature is in Preview. To learn more, see Use prompt templates.
September 25, 2024
Announcement
The Llama 3.2 90B model is available in Preview on Vertex AI. Llama 3.2 90B enables developers to build and deploy the latest generative AI models and applications that use Llama's capabilities, such as image reasoning. Llama 3.2 is also designed to be more accessible for on-device applications. For more information, see Llama models.
September 24, 2024
Announcement
New stable versions of Gemini 1.5 Pro (gemini-1.5-pro-002) and Gemini 1.5 Flash (gemini-1.5-flash-002)
are Generally Available. These models introduce broad quality improvements over the previous 001 versions, with significant gains in the following categories:
Factuality and reduce model hallucinations
Openbook Q&A for RAG use cases
Instruction following
Multilingual understanding in 102 languages, especially in Korean, French, German, Spanish, Japanese, Russian, and Chinese.
SQL generation
Audio understanding
Document understanding
Long context
Math and reasoning
For more information about differences with the previous model versions, see Model versions and lifecycle.
Feature
Use Gemini to directly analyze YouTube videos and publicly available media (such as images, audio, and video) by using a link. This feature is in Public Preview.
Announcement
The 2M context window with Gemini 1.5 Pro is now in Generally Available, which opens up long-form multimodal use cases that only Gemini can support.
Feature
The new API parameters audioTimestamp, responseLogprob, and logprobs are in Public Preview. For more information, see API reference.
Feature
The Vertex AI prompt optimizer adapts your prompts using the optimal instructions and examples to elicit the best performance from your chosen model. This feature is available in Preview. To learn more, see Optimize prompts.
Change
Gemini 1.5 Pro and Gemini 1.5 Flash Tuning is now available in GA.
Tune Gemini with text, image, audio, and document data types using the latest models:
gemini-1.5-pro-002
gemini-1.5-flash-002
Gemini 1.0 tuning remains in preview.
For more information on tuning Gemini, see Tune Gemini models by using supervised fine-tuning.
Feature
Gemini 1.5 Pro and Gemini 1.5 Flash now support multimodal input with function calling. This feature is in Preview.
Change
The latest versions of Gemini 1.5 Flash (gemini-1.5-flash-002) and Gemini 1.5 Pro (gemini-1.5-pro-002) use dynamic shared quota, which distributes on-demand capacity among all queries being processed. Dynamic shared quota is Generally Available.
Announcement
Controlled generation is now Generally Available.
September 20, 2024
Feature
Add label metadata to generateContent and streamGenerateContent API calls. For details, see Add labels to API calls.
September 18, 2024
Announcement
Model Garden supports an organization policy so that administrators can limit access to certain models and capabilities. For more information, see Control access to Model Garden models
September 03, 2024
Change
Gemini 1.5 Flash (gemini-1.5-flash) supports controlled generation.
August 30, 2024
Feature
Gen AI Evaluation Service is Generally Available. To learn more, see the Gen AI Evaluation Service overview.
August 26, 2024
Change
For controlled generation, you can have the model respond with an enum value in plain text, as defined in your response schema. Set the responseMimeType to text/x.enum. For more information, see Control generated output.
August 22, 2024
Change
AI21 Labs
Managed models from AI21 Labs are available on Vertex AI. To use a AI21 Labs model on Vertex AI, send a request directly to the Vertex AI API endpoint. For more information, see AI21 models.
August 09, 2024
Announcement
Gemini on Vertex AI supports multiple response candidates. For details, see Generate content with the Gemini API.
August 05, 2024
Change
The translation LLM now supports Arabic, Hindi, and Russian. For the full list of supported languages, see the Translate text page.
August 02, 2024
Feature
Vertex AI SDK for Python supports token listing and counting for prompts without the need to make API calls. This feature is available in (Preview). For details, see List and count tokens.
July 31, 2024
Feature
New Imagen on Vertex AI image generation model and features
The Imagen 3 image generation models (imagen-3.0-generate-001 and the low-latency version imagen-3.0-fast-generate-001) are Generally Available to approved users. These models offer the following additional features:
Additional aspect ratios (1:1, 3:4, 4:3, 9:16, 16:9)
Digital watermark (SynthID) enabled by default
Watermark verification
User-configurable safety features (safety setting, person/face setting)
For more information, see Model versions and Generate images using text prompts.
Announcement
Gemma 2 2B is available in Model Garden. For details, see Use Gemma open models.
Feature
The following models have been added to Model Garden:
Gemma 2 2B: A foundation LLM by Google DeepMind.
Qwen2: An LLM series by Alibaba Cloud.
Phi-3: An LLM series by Microsoft.
Change
Resource and deployment settings were made to the following models:
Added GPU inferences for gemma2-27b and gemma2-27b-it with verified performances.
Added verified deployment settings for Mistral AI models that are deployed from Huggingface, including mistralai/mistral-nemo-instruct-2407, mistralai/mistral-nemo-base-2407, mistralai/mistral-large-instruct-2407, and mistralai/codestral-22b-v0.1.
Added multiple deployment settings with A100 (40G), A100 (80G) and H100 (80G) for select models, such as llama3.1, llama3, gemma2, gemma, and mistral-7b.
July 30, 2024
Announcement
See the Gemini Online Inference on Vertex AI Service Level Agreement (SLA).
July 24, 2024
Announcement
Mistral AI
Managed models from Mistral AI are available on Vertex AI. To use a Mistral AI model on Vertex AI, send a request directly to the Vertex AI API endpoint. For more information, see Mistral AI models.
July 23, 2024
Announcement
Llama 3.1
The Llama 3.1 405B model is available in Preview on Vertex AI. Llama 3.1 405B provides capabilities from synthetic data generation to model distillation, steerability, math, tool use, multilingual translation, and more. For more information, see Llama models.
July 02, 2024
Announcement
Google's open weight Gemma 2 model is available in Model Garden. For details, see Use Gemma open models.
Change
MaMMUT is now available in Model Garden. MaMMUT is a vision-encoder and text-decoder model for multimodal tasks such as visual question answering, image-text retrieval, text-image retrieval, and generation of multimodal embeddings.
June 28, 2024
Feature
Launched Hex-LLM for high-efficiency large language model serving. This performant TPU serving solution is based on XLA and optimized kernels to achieve high throughput and low latency.
Hex-LLM uses several parallelism strategies for multiple TPU chips, quantizations, dynamic LoRA, and more. Hex-LLM supports the following dense and sparse LLMs:
Gemma 2B and 7B
Gemma 2 9B and 27B
Llama 2 7B, 13B and 70B
Llama 3 8B and 70B
Mistral 7B and Mixtral 8x7B
Feature
The following models have been added to Model Garden:
36 Hugging Face embedding models with verified deployment settings such as BAAI/bge-m3 and intfloat/multilingual-e5-large-instruct.
35 Hugging Face PyTorch models with verified deployment settings such as stabilityai/stable-diffusion-2-1.
For more information, see the Hugging Face model deployment in the console.
Change
Updated Docker images in Llama 3 notebooks that are more efficient at tuning.
A notebook-based interactive workshop UI was added in Model Garden for image generative models such as stable-diffusion-xl-base, image inpainting, controlnet. You can find these models from the Open Notebook list.
Colab Notebooks for frequently used models in Model Garden have been revised with no-code or low-code implementations to improve accessibility and user experience.
June 27, 2024
Feature
Context caching is available for Gemini 1.5 Pro. Use context caching to reduce the cost of requests that contain repeat content with high input token counts. For more information, see Context caching overview.
June 25, 2024
Feature
Controlled generation is available on Gemini 1.5 Pro and supports the JSON schema. For more information, see Control generated output.
June 20, 2024
Announcement
The Anthropic Claude Sonnet 3.5 is Generally Available. To learn more, view the Claude Sonnet 3.5 model card in Model Garden.
June 17, 2024
Change
Increased the input token limit for Gemini 1.5 Pro from 1M to 2M. For more information, see Google models.
June 11, 2024
Change
Upload media from Google Drive
You can upload media, such as PDF, MP4, WAV, and JPG files from Google Drive, when you send image, video, audio, and document prompt requests.
June 10, 2024
Feature
Experiment in the Vertex AI Studio login-free
The Vertex AI Studio multi-model prompt designer can be accessed login-free. With this feature, prospective customers can use the Vertex AI Studio to test queries before deciding to sign up and create an account. To learn more about this experience, see Vertex AI Studio console experiences or to access the console directly go to Vertex AI Studio.
May 31, 2024
Change
Generative AI on Vertex AI Regional APIs
Generative AI on Vertex AI regional APIs are available in the following three regions:
us-east5
me-central1
me-central2
Change
Anthropic Claude 3.0 Opus model
The Anthropic Claude 3.0 Opus model is Generally Available. To learn more, see its model card in Model Garden.
May 28, 2024
Feature
Gemini models support the frequencyPenalty and presencePenalty parameters. Use frequencyPenalty to control the probability of repeated text in a response. Use presencePenalty to control the probability of generating more diverse content. For more information, see Gemini model parameters.
May 24, 2024
Announcement
The Gemini 1.5 Pro (gemini-1.5-pro-001) and Gemini 1.5 Flash (gemini-1.5-flash-001) models are Generally Available. For more information, see Google models, Overview of the Gemini API, and Send multimodal prompt requests.
May 20, 2024
Feature
The following models have been added to Model Garden:
E5: A text embedding model series that can be served with a GPU or CPU.
Instant ID: An identity preserving text-to-image generation model.
Stable Diffusion XL lightning: A text-to-image generation model that is based on SDXL but requires fewer inference iterations.
To see a list of all available models, see Explore models in Model Garden.
May 14, 2024
Announcement
Gemini 1.5 Flash (Preview)
Gemini 1.5 Flash (gemini-1.5-flash-preview-0514) is available in Preview. Gemini 1.5 Flash is a multimodal model designed for fast, high volume, cost-effective text generation and chat applications. It can analyze text, code, audio, PDF, video, and video with audio.
Announcement
PaliGemma model
The PaliGemma model is available. PaliGemma is a lightweight open model that's part of the Google Gemma model family. It's the Gemma model family's best model option for image captioning tasks and visual question and answering tasks. Gemma models are based on Gemini models and intended to be extended by customers.
Feature
Grounding Gemini with Google Search is GA
The Gemini API Grounding with Google Search feature is available in GA. This is available for Gemini 1.0 Pro models. To learn more about model grounding, see Grounding with Google Search.
Feature
Batch prediction support for Gemini
Batch prediction is available for Gemini in preview. Available Gemini models include Gemini 1.0 Pro, Gemini 1.5 Pro, and Gemini 1.5 Flash. To get started with batch prediction, see Get batch predictions for Gemini.
Feature
New stable text embedding models
The following text embedding models are available GA:
text-embedding-004
text-multilingual-embedding-002
For details on how to use these models, see Get text embeddings.
April 18, 2024
Feature
Meta's open weight Llama 3 model is available in the Vertex AI Model Garden.
April 11, 2024
Announcement
Anthropic Claude 3.0 Opus model
The Anthropic Claude 3.0 Opus model is available in Preview. The Claude 3.0 Opus model is an Anthropic partner model that you can use with Vertex AI. It's the most capable of the Anthropic models at performing complex tasks quickly. To learn more, see its model card in Model Garden.
April 09, 2024
Change
Change in Imagen image generation version 006 (imagegeneration@006) seed field behavior
For the new Imagen image generation model version 006 (imagegeneration@006) the seed field behavior has changed. For the v.006 model a digital watermark is enabled by default for image generation. To be able to use a seed value to get deterministic output you must disable digital watermark generation by setting the following parameter: "addWatermark": false.
For more information, see the Imagen for image generation and editing API reference.
Feature
New Imagen on Vertex AI image editing model and features
The 006 version of the Imagen 2 image editing model (imagegeneration@006) is now available. This model offers the following additional features:
Inpainting - Add or remove content from a masked area of an image
Outpainting - Expand a masked area of an image
Product image editing - Identify and maintain a primary product while changing the background or product position
For more information, see Model versions.
Feature
New Imagen on Vertex AI image generation model and features
The 006 version of the Imagen 2 image generation model (imagegeneration@006) is now available. This model offers the following additional features:
Additional aspect ratios (1:1, 3:4, 4:3, 9:16, 16:9)
Digital watermark (SynthID) enabled by default
Watermark verification*
New user-configurable safety features (safety setting, person/face setting)
For more information, see Model versions and Generate images using text prompts.
* The seed field can't be used while digital watermark is enabled.
Feature
Grounding Gemini and Grounding with Google Search
The Gemini API now supports Grounding with Google Search in Preview. Currently available for Gemini 1.0 Pro models.
Feature
Online Evaluation Service
Generative AI evaluation supports online evaluation in addition to pipeline evaluation. The list of supported evaluation metrics has also expanded. See API reference and SDK reference.
Feature
Supervised Tuning for Gemini
Supervised tuning is available for the gemini-1.0-pro-002 model.
Change
Generative AI Knowledge Base
The Jump Start Solution: Generative AI Knowledge Base demonstrates how to build a simple chatbot with business- and domain-specific knowledge.
Feature
New text embedding models
The following text embedding models are now in Preview.
text-embedding-preview-0409
text-multilingual-embedding-preview-0409
When evaluated using the MTEB benchmarks, these models produce better embeddings compared to previous versions. The new models also offer dynamic embedding sizes, which you can use to output smaller embedding dimensions, with minor performance loss, to save on computing and storage costs.
For details on how to use these models, refer to the public documentation and try out our Colab.
Feature
System instructions
System instructions are supported in Preview by the Gemini 1.0 Pro (stable version gemini-1.0-pro-002 only) and Gemini 1.5 Pro (Preview) multimodal models. Use system instructions to guide model behavior based on your specific needs and use cases. For more information, see System instructions examples.
Change
Regional APIs
Regional APIs are available in 11 new countries for Gemini, Imagen, and embeddings.
US and EU have machine-learning processing boundaries for the gemini-1.0-pro-001, gemini-1.0-pro-002, gemini-1.0-pro-vision-001, and imagegeneration@005 models.
Feature
Text translation
Translate text in Vertex AI Studio is available in Preview.
Announcement
Gemini 1.0 Pro stable version 002
The 002 version of the Gemini 1.0 Pro multimodal model (gemini-1.0-pro-002) is available. For more information about stable versions of Gemini models, see Gemini model versions and lifecycle.
Feature
Generative AI on Vertex AI security control update
Security controls are available for the online prediction feature for Gemini 1.0 Pro and Gemini 1.0 Pro Vision.
Change
Vertex AI Studio features and updates
The Vertex AI Studio supports side-by-side comparison to allow users to compare up to 3 prompts in a side-by-side view.
The Vertex AI Studio supports rapid evaluation in console and the ability to upload a ground truth response (or a model response to try to emulate).
To learn more, see Try your prompts in Vertex AI Studio
Announcement
CodeGemma model
The CodeGemma model is available. CodeGemma is a lightweight open model that's part of the Google Gemma model family. CodeGemma is the Gemma model family's code generation and code completion offering. Gemma models are based on Gemini models and intended to be extended by customers.
Announcement
Gemini 1.5 Pro (Preview)
Gemini 1.5 Pro (gemini-1.5-pro-preview-0409) is available in Preview. Gemini 1.5 Pro is a multimodal model that analyzes text, code, audio, PDF, video, and video with audio.
April 02, 2024
Feature
Model Garden supports all Text Generation Inference supported models in HuggingFace:
Verified deployment settings for about 400 Hugging Face text generation models (including google/gemma-7b-it, meta-llama/Llama-2-7b-chat-hf, and mistralai/Mistral-7B-v0.1).
Other Hugging Face text generation models have unverified deployment settings that are auto generated.
March 29, 2024
Change
The MedLM-large model infrastructure has been upgraded to improve
latency and stability. Responses from the model might be slightly different.
Send feedback
Except as otherwise noted, the content of this page is licensed under the Creative Commons Attribution 4.0 License, and code samples are licensed under the Apache 2.0 License. For details, see the Google Developers Site Policies. Java is a registered trademark of Oracle and/or its affiliates.
Last updated 2026-08-26 UTC.
Need to tell us more?
[[["Easy to understand","easyToUnderstand","thumb-up"],["Solved my problem","solvedMyProblem","thumb-up"],["Other","otherUp","thumb-up"]],[["Hard to understand","hardToUnderstand","thumb-down"],["Incorrect information or sample code","incorrectInformationOrSampleCode","thumb-down"],["Missing the information/samples I need","missingTheInformationSamplesINeed","thumb-down"],["Other","otherDown","thumb-down"]],["Last updated 2026-08-26 UTC."],[],[]]