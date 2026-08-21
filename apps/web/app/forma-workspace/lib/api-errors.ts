import type { ApiErrorDetails } from "../types";

export function normalizeApiErrorDetails(value: any, fallback: string): ApiErrorDetails {
  if (typeof value === "string" && value.trim()) {
    return { message: value.trim() };
  }

  if (Array.isArray(value)) {
    const messages = value
      .map((item: any) => item?.msg || item?.message || item?.detail)
      .filter(Boolean);
    if (messages.length) return { message: messages.join("; ") };
  }

  if (value && typeof value === "object") {
    const message =
      typeof value.message === "string"
        ? value.message
        : typeof value.detail === "string"
          ? value.detail
          : fallback;
    const reason = typeof value.reason === "string" ? value.reason : undefined;
    const provider = typeof value.provider === "string" ? value.provider : undefined;
    const model = typeof value.model === "string" ? value.model : undefined;
    return {
      message,
      code: typeof value.code === "string" ? value.code : undefined,
      reason,
      provider,
      model,
      job_id: typeof value.job_id === "string" ? value.job_id : undefined,
      debug: value.debug && typeof value.debug === "object" ? value.debug : undefined,
    };
  }

  return { message: fallback };
}

export async function readApiError(response: Response): Promise<ApiErrorDetails> {
  const fallback = `Server returned ${response.status}`;
  try {
    const body = await response.json();
    if (body?.detail !== undefined) return normalizeApiErrorDetails(body.detail, fallback);
    if (body?.message !== undefined) return normalizeApiErrorDetails(body.message, fallback);
    if (body?.error !== undefined) return normalizeApiErrorDetails(body.error, fallback);
  } catch {
    // Fall through to a generic message.
  }

  return { message: fallback };
}

export async function readApiErrorMessage(response: Response) {
  return (await readApiError(response)).message;
}
