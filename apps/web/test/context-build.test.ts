import assert from "node:assert/strict";
import { test } from "node:test";

import {
  contextBuildWatchKey,
  isActiveBuildStatus,
  shouldResumeDetachedBuild,
} from "../app/forma-workspace/lib/context-build";

test("detached resume is skipped when this client is already watching", () => {
  assert.equal(
    shouldResumeDetachedBuild({ requestBoundExecution: false, alreadyWatching: true }),
    false,
  );
  assert.equal(
    shouldResumeDetachedBuild({ requestBoundExecution: false, alreadyWatching: false }),
    true,
  );
});

test("request-bound runtimes never resume via detached launch", () => {
  assert.equal(
    shouldResumeDetachedBuild({ requestBoundExecution: true, alreadyWatching: false }),
    false,
  );
  assert.equal(isActiveBuildStatus("planned"), true);
  assert.equal(isActiveBuildStatus("succeeded"), false);
  assert.equal(contextBuildWatchKey("proj", "plan"), "proj:plan");
});
