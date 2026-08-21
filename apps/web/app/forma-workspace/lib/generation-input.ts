export function validateGenerationInput(value: string, hasImage: boolean) {
  const promptText = value.trim();
  if (!promptText) {
    return {
      isValid: hasImage,
      message: hasImage ? null : "Provide a prompt or reference image.",
    };
  }

  return {
    isValid: true,
    message: null,
  };
}
