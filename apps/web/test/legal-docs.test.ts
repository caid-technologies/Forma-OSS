import assert from "node:assert/strict";
import { test } from "node:test";

import {
  documentsForSlugs,
  getLegalDocument,
  legalDocumentMatchesQuery,
  legalDocuments,
  primaryLegalSlugs,
  secondaryLegalSlugs,
} from "../lib/legal-docs";

test("every published legal document is in the primary or reporting nav", () => {
  const navSlugs = [...primaryLegalSlugs, ...secondaryLegalSlugs];
  assert.deepEqual(
    [...navSlugs].sort(),
    legalDocuments.map((document) => document.slug).sort(),
  );
  assert.equal(documentsForSlugs(navSlugs).length, legalDocuments.length);
});

test("legal search matches titles, summaries, and body copy", () => {
  const privacy = getLegalDocument("privacy-policy");
  assert.ok(privacy);
  assert.equal(legalDocumentMatchesQuery(privacy, ""), true);
  assert.equal(legalDocumentMatchesQuery(privacy, "privacy"), true);
  assert.equal(legalDocumentMatchesQuery(privacy, "not-a-real-policy-phrase"), false);

  const dmca = getLegalDocument("copyright-dmca-policy");
  assert.ok(dmca);
  assert.equal(legalDocumentMatchesQuery(dmca, "copyright"), true);
});
