export type ClipboardWriter = {
  writeText: (text: string) => Promise<void>;
};

export type CopyEnvironment = {
  /** The async clipboard API, when the browser exposes one. */
  clipboard?: ClipboardWriter | null;
  /** Async clipboard writes are rejected outside a secure context. */
  isSecureContext?: boolean;
  /** Synchronous `document.execCommand("copy")` path for older or non-secure contexts. */
  legacyCopy?: ((text: string) => boolean) | null;
};

/**
 * Copies `text` using the async clipboard API, falling back to the legacy
 * selection-based command when it is unavailable or rejected. Returns whether
 * the text actually made it to the clipboard so callers can surface a failure
 * instead of silently pretending the copy worked.
 */
export async function copyTextToClipboard(text: string, environment: CopyEnvironment): Promise<boolean> {
  if (!text) return false;

  const { clipboard, isSecureContext = true, legacyCopy } = environment;

  if (clipboard && isSecureContext) {
    try {
      await clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied, a detached document, or a browser that rejects
      // writes outside a user gesture: fall through to the legacy path.
    }
  }

  if (legacyCopy) {
    try {
      return legacyCopy(text);
    } catch {
      return false;
    }
  }

  return false;
}

function legacyDocumentCopy(text: string): boolean {
  const { body } = document;
  if (!body) return false;

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.setAttribute("aria-hidden", "true");
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "0";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";

  const previouslyFocused = document.activeElement as HTMLElement | null;
  body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  try {
    return document.execCommand("copy");
  } finally {
    body.removeChild(textarea);
    previouslyFocused?.focus?.();
  }
}

/** Reads the copy capabilities of the current browser. Server-safe: returns an empty environment. */
export function browserCopyEnvironment(): CopyEnvironment {
  if (typeof navigator === "undefined" || typeof document === "undefined") return {};

  return {
    clipboard: navigator.clipboard ?? null,
    isSecureContext: typeof window === "undefined" ? true : window.isSecureContext !== false,
    legacyCopy: typeof document.execCommand === "function" ? legacyDocumentCopy : null,
  };
}

/** Convenience wrapper around {@link copyTextToClipboard} bound to the current browser. */
export function copyText(text: string): Promise<boolean> {
  return copyTextToClipboard(text, browserCopyEnvironment());
}
