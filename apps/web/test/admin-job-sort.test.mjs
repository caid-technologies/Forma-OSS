import assert from "node:assert/strict";
import { test } from "node:test";

import {
  adminJobLastOccurredAt,
  sortAdminJobs,
} from "../lib/admin-job-sort";

const jobs = [
  {
    job_id: "old-created-recent-update",
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-09T12:00:00Z",
  },
  {
    job_id: "new-created",
    created_at: "2026-08-08T10:00:00Z",
    updated_at: "2026-08-08T10:00:00Z",
  },
  { job_id: "unknown-time", created_at: "invalid" },
];

test("last occurred uses the latest lifecycle timestamp", () => {
  assert.equal(adminJobLastOccurredAt({
    job_id: "completed",
    created_at: "2026-08-01T10:00:00Z",
    started_at: "2026-08-01T10:01:00Z",
    updated_at: "2026-08-01T10:02:00Z",
    completed_at: "2026-08-01T10:03:00Z",
  }), "2026-08-01T10:03:00.000Z");
});

test("recent last occurrence moves updated jobs ahead of newer created jobs", () => {
  const sorted = sortAdminJobs(jobs, "last_occurred_desc");

  assert.deepEqual(sorted.map((job) => job.job_id), [
    "old-created-recent-update",
    "new-created",
    "unknown-time",
  ]);
});

test("last occurred supports oldest-first ordering and keeps missing dates last", () => {
  const sorted = sortAdminJobs(jobs, "last_occurred_asc");

  assert.deepEqual(sorted.map((job) => job.job_id), [
    "new-created",
    "old-created-recent-update",
    "unknown-time",
  ]);
});

test("created ordering is available and does not mutate the input", () => {
  const originalOrder = jobs.map((job) => job.job_id);
  const sorted = sortAdminJobs(jobs, "created_desc");

  assert.deepEqual(sorted.map((job) => job.job_id), [
    "new-created",
    "old-created-recent-update",
    "unknown-time",
  ]);
  assert.deepEqual(jobs.map((job) => job.job_id), originalOrder);
});
