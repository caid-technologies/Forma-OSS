# OpenCode model switching and OpenAI images

The agent model and image model are independent. An OpenCode agent using a
Google model can call Forma's OpenAI image tool.

## Switch the agent model

In the Forma Agent banner, enter a `provider/model` ID and select **Apply**.
The selector remembers the last eight choices in this browser. Select an earlier
choice to switch again, or select **Runtime default** to remove the override.
Changes affect the next submitted command, including in an existing conversation.
Queued commands keep their explicit model when leased again after a restart.

The list contains your saved choices, not a live catalogue of the mini-PC's
credentials or model entitlements. Use `opencode models` on the runtime to find
IDs supported by its providers. The selected model must be usable by the account
running the connector. An unavailable explicit model fails through OpenCode's
normal error path; the connector does not retry it with another model.

Resolution order:

1. `model` on the Forma command, if supplied.
2. Optional `FORMA_OPENCODE_MODEL` in the connector service environment.
3. OpenCode's own configuration/default resolution for that process.

The connector passes the resolved explicit choice as
`model: { providerID, modelID }` to `POST /session/:id/prompt_async`.
Model IDs may contain further slashes (for example, an OpenRouter model).
The generated project policy continues to own the restricted agent and tools.
The picker does not rewrite the user's global OpenCode config or credentials.

OpenCode's interactive `/models` selection affects that OpenCode environment;
the service can run under a different Windows account and creates fresh local
sessions. Use the Forma picker or an explicit service default for predictable
hosted requests. Null commands deliberately inherit the default at execution
time; only explicit command selections are pinned across retries.

## Generate an OpenAI image

Ask Forma Agent to generate a concept image of the saved project. The restricted
MCP surface includes `forma.opencode.generate_image` with two arguments:

```json
{
  "prompt": "Generate an isometric concept image of this bracket",
  "request_id": "bracket-concept-1"
}
```

The capability supplies project and owner identity. The tool calls the existing
`OpenAIImageProvider`, generates one image, and attaches it to a project revision
through Forma's existing image storage and project persistence. It does not run
CAD generation. The project preview displays the saved image after the command
completes and the workspace reloads the project. Future IR edits preserve that
image. Image bytes and storage URLs are omitted from restricted project-tool
responses to avoid putting them in the agent context.

Configure these settings on the **Forma backend serving the restricted MCP URL**:

```dotenv
# Supply the key securely in the backend environment; do not commit it.
OPENAI_IMAGE_API_KEY=<your OpenAI API key>
OPENAI_IMAGE_BASE_URL=https://api.openai.com/v1
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1024x1024
OPENAI_IMAGE_QUALITY=medium
OPENAI_IMAGE_OUTPUT_FORMAT=png
```

`OPENAI_API_KEY` is the existing fallback if `OPENAI_IMAGE_API_KEY` is absent.
The example keeps Forma's existing image-model default; choose another supported
GPT Image model explicitly if your OpenAI project has access. OpenCode login
credentials are not a substitute for the backend image API key. This tool uses
OpenAI independently of `IMAGE_PROVIDER` used by other Forma generation flows.
Images are generated only by an explicit tool call, not on every authoring turn.

Reuse `request_id` for a retry of a saved image request. A completed request
returns its existing revision without another provider call; changing the prompt
under that ID is rejected. This is completed-request deduplication, not an
exactly-once billing guarantee: a crash after the provider succeeds but before
the revision is stored, or simultaneous requests on separate backend workers,
can generate twice. No provider calls are automatically retried by this tool.

Concept images do not establish CAD geometry, dimensions, or manufacturability.
Storage/provider errors return bounded messages without raw provider responses.

## Deploy the paired changes

1. Apply `20260917000100_opencode_command_model.sql` to Supabase before running
   the new backend. Existing SQLite databases add the nullable column on startup.
2. Deploy the Forma backend and set its OpenAI image credentials/model.
3. Deploy the paired `local-server-config` connector update and restart its
   service. Existing commands without a model remain compatible.
4. Deploy the Forma web update after the connector. An older connector ignores
   the new model field and does not allow the image tool.
5. Verify on the mini-PC: send two requests with different available model IDs,
   return to Runtime default, generate one image, reload the project, then make
   a CAD edit and confirm the image remains.

Local automated checks use simulated provider/connector responses. Live OpenCode
model access, paid OpenAI generation and Windows service rollout require host
acceptance after deployment.

## References

- [OpenCode model selection](https://opencode.ai/docs/models/)
- [OpenCode server API](https://opencode.ai/docs/server/)
- [OpenAI image generation API](https://developers.openai.com/api/docs/guides/image-generation)
