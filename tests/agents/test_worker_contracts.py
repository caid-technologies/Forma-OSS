from __future__ import annotations

import unittest
import uuid

from pydantic import ValidationError

from blueprint_core.workers import (
    WORKER_CONTRACT_VERSION,
    WorkerArtifact,
    WorkerCapability,
    WorkerDefinition,
    WorkerDependency,
    WorkerError,
    WorkerProgress,
    WorkerRegistry,
    WorkerRegistryError,
    WorkerRequest,
    WorkerResult,
)


PROJECT_ID = uuid.UUID("83b48573-a513-4e51-a562-24d4d1f6c250")
DESIGN_BRIEF_ID = uuid.UUID("8a44549f-7508-4307-a864-4895d0d2f877")


def contract_context(
    *,
    worker_id: str = "electrical-worker",
    capability_id: str = "electrical.plan",
) -> dict[str, object]:
    return {
        "contract_version": WORKER_CONTRACT_VERSION,
        "project_id": PROJECT_ID,
        "project_revision": 3,
        "design_brief_id": DESIGN_BRIEF_ID,
        "design_brief_version": 2,
        "job_id": "job_worker_123",
        "correlation_id": "corr_build_456",
        "worker_id": worker_id,
        "capability_id": capability_id,
    }


class FakeElectricalWorker:
    def __init__(self) -> None:
        self.execution_count = 0

    def worker_definition(self) -> WorkerDefinition:
        return WorkerDefinition(
            worker_id="electrical-worker",
            name="Fake Electrical Worker",
            worker_version="0.1.0",
            capabilities=[
                WorkerCapability(
                    capability_id="electrical.plan",
                    description="Create an electrical plan.",
                    supported_input_versions=["design-brief.v1"],
                    supported_output_versions=["electrical-plan.v1"],
                ),
                WorkerCapability(
                    capability_id="hardware.review",
                    description="Review a hardware plan.",
                    supported_input_versions=["hardware-review.v1"],
                    supported_output_versions=["review-findings.v1"],
                ),
            ],
        )

    def execute(self, request: WorkerRequest) -> dict[str, object]:
        self.execution_count += 1
        return request.payload


class FakeMechanicalWorker:
    def worker_definition(self) -> WorkerDefinition:
        return WorkerDefinition(
            worker_id="mechanical-worker",
            name="Fake Mechanical Worker",
            worker_version="0.2.0",
            capabilities=[
                WorkerCapability(
                    capability_id="mechanical.enclosure",
                    description="Create an enclosure plan.",
                    supported_input_versions=["design-brief.v1", "mechanical-request.v1"],
                    supported_output_versions=["enclosure-plan.v1"],
                ),
                WorkerCapability(
                    capability_id="hardware.review",
                    description="Review mechanical fit.",
                    supported_input_versions=["hardware-review.v1"],
                    supported_output_versions=["review-findings.v1"],
                ),
            ],
        )


class WorkerContractTests(unittest.TestCase):
    def test_request_round_trip_carries_context_dependencies_and_correlation(self) -> None:
        request = WorkerRequest(
            **contract_context(),
            input_contract_version="design-brief.v1",
            dependencies=[
                WorkerDependency(
                    dependency_id="dep_context",
                    job_id="job_context_001",
                    worker_id="context-worker",
                    capability_id="context.finalize",
                )
            ],
            payload={"requested_outputs": ["wiring", "bom"]},
        )

        restored = WorkerRequest.model_validate_json(request.model_dump_json())

        self.assertEqual(request, restored)
        self.assertEqual(PROJECT_ID, restored.project_id)
        self.assertEqual(3, restored.project_revision)
        self.assertEqual(DESIGN_BRIEF_ID, restored.design_brief_id)
        self.assertEqual(2, restored.design_brief_version)
        self.assertEqual("job_context_001", restored.dependencies[0].job_id)
        self.assertEqual("corr_build_456", restored.correlation_id)

    def test_progress_artifacts_errors_and_results_have_stable_serializable_shapes(self) -> None:
        progress = WorkerProgress(
            **contract_context(),
            sequence=4,
            status="running",
            percent_complete=62.5,
            message="Routing power rails",
        )
        artifact = WorkerArtifact(
            **contract_context(),
            artifact_id="artifact_wiring",
            kind="wiring-diagram",
            uri="s3://worker-artifacts/wiring.svg",
            media_type="image/svg+xml",
        )
        error = WorkerError(
            **contract_context(),
            error_id="error_catalog_timeout",
            code="catalog_timeout",
            message="The component catalog timed out.",
            retryable=True,
            details={"provider": "catalog"},
        )
        failed = WorkerResult(
            **contract_context(),
            output_contract_version="electrical-plan.v1",
            status="failed",
            error=error,
        )
        succeeded = WorkerResult(
            **contract_context(),
            output_contract_version="electrical-plan.v1",
            status="succeeded",
            output={"rail_count": 2},
            artifacts=[artifact],
        )

        self.assertEqual(progress, WorkerProgress.model_validate_json(progress.model_dump_json()))
        self.assertEqual(artifact, WorkerArtifact.model_validate_json(artifact.model_dump_json()))
        self.assertEqual(error, WorkerError.model_validate_json(error.model_dump_json()))
        self.assertEqual(failed, WorkerResult.model_validate_json(failed.model_dump_json()))
        self.assertEqual(succeeded, WorkerResult.model_validate_json(succeeded.model_dump_json()))

    def test_envelopes_reject_unsupported_versions_with_a_structured_error(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            WorkerRequest(
                **{**contract_context(), "contract_version": "2.0"},
                input_contract_version="design-brief.v1",
            )

        error = raised.exception.errors()[0]
        self.assertEqual("unsupported_worker_contract_version", error["type"])
        self.assertEqual(["1.0"], error["ctx"]["supported_versions"])

    def test_results_validate_terminal_status_and_nested_context(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires error details"):
            WorkerResult(
                **contract_context(),
                output_contract_version="electrical-plan.v1",
                status="failed",
            )

        wrong_artifact = WorkerArtifact(
            **contract_context(worker_id="mechanical-worker"),
            kind="enclosure",
            uri="s3://worker-artifacts/enclosure.step",
        )
        with self.assertRaisesRegex(ValidationError, "context must match"):
            WorkerResult(
                **contract_context(),
                output_contract_version="electrical-plan.v1",
                status="succeeded",
                artifacts=[wrong_artifact],
            )


class WorkerRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.electrical = FakeElectricalWorker()
        self.mechanical = FakeMechanicalWorker()
        self.registry = WorkerRegistry([self.electrical, self.mechanical])

    def request(
        self,
        *,
        worker_id: str = "electrical-worker",
        capability_id: str = "electrical.plan",
        input_contract_version: str = "design-brief.v1",
    ) -> WorkerRequest:
        return WorkerRequest(
            **contract_context(worker_id=worker_id, capability_id=capability_id),
            input_contract_version=input_contract_version,
            payload={"summary": "Build a controller"},
        )

    def test_two_workers_declare_discoverable_capabilities_and_versions(self) -> None:
        manifest = self.registry.manifest()
        reviewers = self.registry.find_capability(
            "hardware.review",
            input_contract_version="hardware-review.v1",
        )

        self.assertEqual(
            ["electrical-worker", "mechanical-worker"],
            [item["worker_id"] for item in manifest["workers"]],
        )
        self.assertEqual(
            ["electrical-worker", "mechanical-worker"],
            [resolution.worker.worker_id for resolution in reviewers],
        )
        electrical = self.registry.resolve("electrical-worker", "electrical.plan")
        self.assertEqual(["design-brief.v1"], electrical.capability.supported_input_versions)
        self.assertEqual(["electrical-plan.v1"], electrical.capability.supported_output_versions)

    def test_unknown_worker_and_capability_fail_before_execution(self) -> None:
        for request, expected_code in (
            (self.request(worker_id="missing-worker"), "unknown_worker"),
            (self.request(capability_id="electrical.fabricate"), "unknown_worker_capability"),
        ):
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(WorkerRegistryError) as raised:
                    self.registry.validate_request(request)
                    self.electrical.execute(request)
                self.assertEqual(expected_code, raised.exception.code)
                self.assertEqual(expected_code, raised.exception.as_dict()["code"])

        self.assertEqual(0, self.electrical.execution_count)

    def test_request_and_result_versions_are_checked_against_capability(self) -> None:
        with self.assertRaises(WorkerRegistryError) as input_error:
            self.registry.validate_request(self.request(input_contract_version="design-brief.v2"))

        result = WorkerResult(
            **contract_context(),
            output_contract_version="electrical-plan.v2",
            status="succeeded",
        )
        with self.assertRaises(WorkerRegistryError) as output_error:
            self.registry.validate_result(result)

        self.assertEqual("incompatible_worker_contract_version", input_error.exception.code)
        self.assertEqual("input", input_error.exception.context["direction"])
        self.assertEqual(["design-brief.v1"], input_error.exception.context["supported_versions"])
        self.assertEqual("incompatible_worker_contract_version", output_error.exception.code)
        self.assertEqual("output", output_error.exception.context["direction"])

    def test_compatible_request_is_resolved_before_worker_execution(self) -> None:
        request = self.request()

        resolution = self.registry.validate_request(request)
        output = self.electrical.execute(request)

        self.assertEqual("electrical-worker", resolution.worker.worker_id)
        self.assertEqual({"summary": "Build a controller"}, output)
        self.assertEqual(1, self.electrical.execution_count)


if __name__ == "__main__":
    unittest.main()
