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


## PDF references

The chat composer accepts text-based PDF references in addition to images. PDF files are sent to the context endpoint as `document` attachments with `media_type: application/pdf`. The API extracts bounded text, merges that text into the DesignBrief, and drops the raw PDF data before persisting the reference or chat history.

Current ingestion limits are 2 MB, 40 pages, and 20,000 extracted characters per PDF. Password-protected PDFs and scanned/image-only PDFs are rejected with a clear context-ingestion error; OCR is not performed yet.

```json
{
  "kind": "document",
  "name": "motor-datasheet.pdf",
  "media_type": "application/pdf",
  "data_url": "data:application/pdf;base64,...",
  "source": "upload"
}
```
