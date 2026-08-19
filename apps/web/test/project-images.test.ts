import assert from "node:assert/strict";
import { test } from "node:test";

import {
  HARDWARE_REFERENCE_LABEL,
  hardwareReferenceSrcFromChatMessages,
  isHardwareReferenceCandidate,
  resolveProjectImageCandidates,
  withHardwareReferenceMetadata,
} from "../lib/project-images";

test("generated product views keep the hardware reference as a tagged candidate", () => {
  const candidates = resolveProjectImageCandidates({
    product_visual_sequence: [
      { view_id: "case", label: "Case exterior", data: "data:image/png;base64,Y2FzZQ==" },
      { view_id: "inside", label: "Inside", data: "data:image/png;base64,aW5zaWRl" },
      { view_id: "hero", label: "Hero", data: "data:image/png;base64,aGVybw==" },
    ],
    reference_image_data: "data:image/png;base64,cmVm",
  });

  const productImages = candidates.filter((candidate) => !isHardwareReferenceCandidate(candidate));
  const reference = candidates.find(isHardwareReferenceCandidate);

  assert.equal(productImages.length, 3);
  assert.equal(reference?.viewId, "reference");
  assert.equal(reference?.label, HARDWARE_REFERENCE_LABEL);
  assert.equal(reference?.src, "data:image/png;base64,cmVm");
});

test("chat image previews fill in a missing project hardware reference", () => {
  const metadata = withHardwareReferenceMetadata(
    { product_image_data: "data:image/png;base64,cHJvZHVjdA==" },
    hardwareReferenceSrcFromChatMessages([
      { role: "assistant", imagePreview: "data:image/png;base64,aWdub3Jl" },
      { role: "user", imagePreview: "data:image/png;base64,cmVm" },
    ]),
  );
  const candidates = resolveProjectImageCandidates(metadata);

  assert.equal(candidates.find(isHardwareReferenceCandidate)?.src, "data:image/png;base64,cmVm");
  assert.equal(candidates[0]?.src, "data:image/png;base64,cHJvZHVjdA==");
});
