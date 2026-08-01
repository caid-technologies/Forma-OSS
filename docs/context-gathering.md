# Conversational context gathering

New project conversations begin in `gathering_context`. During this phase, Forma accepts text and image or document references, appends an immutable `DesignBrief` version, persists the user and assistant messages, and returns targeted clarification questions.

```http
POST /projects/{project_id}/context/messages
Content-Type: application/json

{
  "conversation_id": "chat-id",
  "text": "Build a USB-C environmental monitor",
  "attachments": [
    {
      "kind": "image",
      "name": "reference.png",
      "media_type": "image/png",
      "data_url": "data:image/png;base64,...",
      "source": "clipboard"
    }
  ]
}
```

The context agent is deterministic and does not call an LLM, enqueue a worker job, or execute tools. Generation, iteration, fabrication, and OpenCAD mutation actions that identify a project in `gathering_context` fail with `tool_execution_blocked_while_gathering_context`. A later readiness/build action must transition the project before those tools can run.

Inline attachment bytes are not copied into the DesignBrief. The brief stores a stable reference plus media/source metadata; extracted document text is merged into its requirements.
