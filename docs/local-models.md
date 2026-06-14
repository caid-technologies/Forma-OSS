# Local Models

Blueprint can use local models in three different places. These are separate on purpose: a fast text model can compile the Hardware IR, a vision model can describe uploaded reference images, and a diffusion model can render product concepts.

## Model Slots

### 1. Structured Hardware LLM

This model turns prompts into typed Hardware IR through the agent pipeline. It must be good at following JSON/schema instructions.

Use an OpenAI-compatible local server:

```env
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=your-local-text-model
LLM_ALLOW_NO_API_KEY=true
LLM_RESPONSE_FORMAT=json_object
LLM_TIMEOUT_SECONDS=180
LLM_TEMPERATURE=0.2
```

Good fits are instruction-tuned local models that reliably emit JSON. Smaller models can work for demos, but larger coding/instruction models tend to produce cleaner Hardware IR.

### 2. Uploaded Image To Text

This model reads an uploaded reference image and writes a concise hardware-oriented description. Blueprint appends that description to the prompt before running the structured hardware pipeline.

This is useful when the structured LLM is text-only. When image-text extraction succeeds, `IMAGE_TEXT_FORWARD_IMAGE=false` means the raw image is not forwarded to the structured LLM.

Ollama vision model:

```env
IMAGE_TEXT_PROVIDER=ollama
IMAGE_TEXT_BASE_URL=http://localhost:11434
IMAGE_TEXT_MODEL=llava:latest
IMAGE_TEXT_FORWARD_IMAGE=false
```

Other useful Ollama vision model names to try:

```env
IMAGE_TEXT_MODEL=llama3.2-vision:11b
IMAGE_TEXT_MODEL=minicpm-v
```

OpenAI-compatible local vision server:

```env
IMAGE_TEXT_PROVIDER=local
IMAGE_TEXT_BASE_URL=http://localhost:1234/v1
IMAGE_TEXT_MODEL=your-local-vision-model
IMAGE_TEXT_ALLOW_NO_API_KEY=true
IMAGE_TEXT_FORWARD_IMAGE=false
```

Use this path for local servers that accept OpenAI-style `/chat/completions` requests with image input.

### 3. Product Image Generation

This model creates the rendered product concept image when the UI's image model toggle is on or API payloads set `generate_image=true`.

OpenAI-compatible local image API:

```env
IMAGE_OUTPUT_ENABLED=false
IMAGE_PROVIDER=local
IMAGE_BASE_URL=http://localhost:8000/v1
IMAGE_MODEL=your-local-image-model
IMAGE_ALLOW_NO_API_KEY=true
IMAGE_SIZE=1024x1024
```

Stable Diffusion WebUI / Automatic1111:

```env
IMAGE_OUTPUT_ENABLED=false
IMAGE_PROVIDER=stable-diffusion-webui
STABLE_DIFFUSION_BASE_URL=http://127.0.0.1:7860
IMAGE_SIZE=1024x1024
STABLE_DIFFUSION_STEPS=24
```

For Stable Diffusion WebUI, start the WebUI with API mode enabled. The loaded checkpoint in the WebUI controls the actual image model. `STABLE_DIFFUSION_MODEL` or `IMAGE_MODEL` is recorded as metadata by Blueprint; it does not switch checkpoints.

## Common Recipes

### Fully Local: Text LLM + Ollama Vision + Stable Diffusion

```env
# Hardware IR generation
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=your-local-instruct-model
LLM_ALLOW_NO_API_KEY=true
LLM_RESPONSE_FORMAT=json_object
LLM_TIMEOUT_SECONDS=180

# Uploaded image understanding
IMAGE_TEXT_PROVIDER=ollama
IMAGE_TEXT_BASE_URL=http://localhost:11434
IMAGE_TEXT_MODEL=llava:latest
IMAGE_TEXT_FORWARD_IMAGE=false

# Product concept image output
IMAGE_OUTPUT_ENABLED=false
IMAGE_PROVIDER=stable-diffusion-webui
STABLE_DIFFUSION_BASE_URL=http://127.0.0.1:7860
IMAGE_SIZE=1024x1024
STABLE_DIFFUSION_STEPS=24
```

### Local Multimodal Structured LLM

Use this when your local OpenAI-compatible LLM server can handle image input directly and still emit reliable JSON.

```env
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=your-local-multimodal-model
LLM_ALLOW_NO_API_KEY=true
LLM_RESPONSE_FORMAT=json_object

IMAGE_TEXT_PROVIDER=none
```

With this setup, uploaded images are passed directly into the structured LLM calls.

### Local Vision Prepass With Hosted Structured LLM

Use this when you want image understanding to stay local, while the Hardware IR generation uses a hosted text model.

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.5
OPENAI_TIMEOUT_SECONDS=300
OPENAI_REASONING_EFFORT=low

IMAGE_TEXT_PROVIDER=ollama
IMAGE_TEXT_BASE_URL=http://localhost:11434
IMAGE_TEXT_MODEL=llava:latest
IMAGE_TEXT_FORWARD_IMAGE=false
```

### Local Product Image Generation Only

Use this when prompt-to-Hardware-IR stays hosted, but generated product imagery should be local.

```env
IMAGE_PROVIDER=stable-diffusion-webui
STABLE_DIFFUSION_BASE_URL=http://127.0.0.1:7860
IMAGE_SIZE=1024x1024
STABLE_DIFFUSION_STEPS=24
```

Leave `IMAGE_OUTPUT_ENABLED=false` if you only want image generation when the UI checkbox or API `generate_image=true` asks for it.

## Environment Reference

| Variable | Used For | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | Hardware IR generation | Use `openai-compatible` for local text or multimodal LLM servers. |
| `LLM_BASE_URL` | Hardware IR generation | Local OpenAI-compatible base URL, for example `http://localhost:1234/v1`. |
| `LLM_MODEL` | Hardware IR generation | Local model ID exposed by your server. |
| `LLM_MODELS` | Hardware IR generation | Optional ordered comma-separated model list; supersedes `LLM_MODEL` and tries each primary model before the job fails. |
| `LLM_FALLBACK_MODELS` | Hardware IR generation | Optional ordered comma-separated fallback model list used when `STRICT_LLM=false`. |
| `LLM_ALLOW_NO_API_KEY` | Hardware IR generation | Set `true` for local servers without auth. |
| `LLM_RESPONSE_FORMAT` | Hardware IR generation | `json_object` is usually safest for local OpenAI-compatible servers. |
| `IMAGE_TEXT_PROVIDER` | Uploaded image understanding | `ollama`, `local`, `openai-compatible`, `openai`, or `none`. |
| `IMAGE_TEXT_BASE_URL` | Uploaded image understanding | Ollama base URL or OpenAI-compatible `/v1` base URL. |
| `IMAGE_TEXT_MODEL` | Uploaded image understanding | Vision-capable model name. |
| `IMAGE_TEXT_ALLOW_NO_API_KEY` | Uploaded image understanding | Set `true` for local OpenAI-compatible vision servers without auth. |
| `IMAGE_TEXT_FORWARD_IMAGE` | Uploaded image understanding | Defaults to `false` after extraction succeeds; set `true` if the structured LLM should also receive the image. |
| `IMAGE_PROVIDER` | Product image generation | `local`, `openai-compatible`, `stable-diffusion-webui`, `openai`, or `none`. |
| `IMAGE_BASE_URL` | Product image generation | Local OpenAI-compatible image endpoint. |
| `IMAGE_MODEL` | Product image generation | Local image model ID or metadata label. |
| `IMAGE_ALLOW_NO_API_KEY` | Product image generation | Set `true` for local OpenAI-compatible image servers without auth. |
| `STABLE_DIFFUSION_BASE_URL` | Product image generation | Stable Diffusion WebUI / Automatic1111 base URL. |
| `STABLE_DIFFUSION_STEPS` | Product image generation | Defaults to `24`. |
| `STABLE_DIFFUSION_CFG_SCALE` | Product image generation | Optional CFG scale for Stable Diffusion WebUI. |
| `STABLE_DIFFUSION_SAMPLER` | Product image generation | Optional sampler name for Stable Diffusion WebUI. |

## Debugging

Check what Blueprint resolved:

```bash
curl http://localhost:8000/debug/config
```

Look for:

- `provider`, `model_name`, and `configured` under `image_text`
- `provider`, `model_name`, `configured`, and `request_capable` under `image_output`
- `provider`, `requested_models`, `candidate_models`, and `actual_model` at the top level for the structured LLM

If local image upload does not affect the project:

- Confirm `IMAGE_TEXT_PROVIDER` is not `none`.
- Confirm the local vision server is running.
- Confirm `IMAGE_TEXT_MODEL` is a vision-capable model.
- Check `assembly_metadata.image_text_error` in the returned project.

If product image generation does nothing:

- Make sure the UI image toggle is on, or send `generate_image=true`.
- Check `IMAGE_PROVIDER`.
- Check `image_output.request_capable` in `/debug/config`.
- For Stable Diffusion WebUI, make sure it was started with API mode enabled and that `STABLE_DIFFUSION_BASE_URL` points to the running WebUI.

## Metadata

When image text extraction runs, Blueprint can store:

- `assembly_metadata.image_text`
- `assembly_metadata.image_text_provider`
- `assembly_metadata.image_text_model`
- `assembly_metadata.image_text_prompt`
- `assembly_metadata.image_text_error`

When product image generation runs, Blueprint can store:

- `assembly_metadata.product_image_data`
- `assembly_metadata.product_image_provider`
- `assembly_metadata.product_image_model`
- `assembly_metadata.product_image_size`
- `assembly_metadata.product_image_prompt`
- `assembly_metadata.product_image_error`
