from __future__ import annotations

import hashlib
import pathlib
import sys
import tempfile
import types
import unittest

from blueprint_core.huggingface_artifacts import (
    HuggingFaceUploadConfig,
    build_artifacts,
    upload_artifacts_to_huggingface,
)


class FakeCommitInfo:
    commit_url = "https://huggingface.co/datasets/test/repo/commit/fake"


class FakeHfApi:
    created_repos: list[dict] = []
    uploaded_files: list[dict] = []

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def create_repo(self, **kwargs):
        self.created_repos.append(kwargs)

    def upload_file(self, **kwargs):
        self.uploaded_files.append(kwargs)
        return FakeCommitInfo()


class HuggingFaceArtifactTests(unittest.TestCase):
    def test_build_artifacts_records_checksum_size_and_repo_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            artifact_path = root / ".logs" / "benchmarks" / "report.json"
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_text('{"ok": true}\n', encoding="utf-8")

            artifacts = build_artifacts(
                [artifact_path],
                artifact_type="benchmarks/model",
                path_prefix="blueprint",
                root_dir=root,
            )

            expected_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            self.assertEqual(1, len(artifacts))
            self.assertEqual(expected_digest, artifacts[0].sha256)
            self.assertEqual(13, artifacts[0].size_bytes)
            self.assertEqual("blueprint/benchmarks/model/.logs/benchmarks/report.json", artifacts[0].path_in_repo)

    def test_upload_artifacts_uses_hf_api_without_network(self) -> None:
        fake_module = types.ModuleType("huggingface_hub")
        fake_module.HfApi = FakeHfApi
        previous_module = sys.modules.get("huggingface_hub")
        sys.modules["huggingface_hub"] = fake_module
        FakeHfApi.created_repos.clear()
        FakeHfApi.uploaded_files.clear()

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = pathlib.Path(temp_dir)
                artifact_path = root / "metrics.json"
                artifact_path.write_text('{"score": 1}\n', encoding="utf-8")
                artifact = build_artifacts(
                    [artifact_path],
                    artifact_type="evals",
                    path_prefix="blueprint",
                    root_dir=root,
                )[0]

                result = upload_artifacts_to_huggingface(
                    [artifact],
                    config=HuggingFaceUploadConfig(
                        repo_id="test/repo",
                        token="hf_test",
                        private=True,
                        path_prefix="blueprint",
                    ),
                )
        finally:
            if previous_module is None:
                sys.modules.pop("huggingface_hub", None)
            else:
                sys.modules["huggingface_hub"] = previous_module

        self.assertEqual(1, result.count)
        self.assertEqual("test/repo", result.repo_id)
        self.assertEqual("dataset", FakeHfApi.created_repos[0]["repo_type"])
        self.assertTrue(FakeHfApi.created_repos[0]["private"])
        self.assertEqual("test/repo", FakeHfApi.uploaded_files[0]["repo_id"])
        self.assertEqual("blueprint/evals/metrics.json", FakeHfApi.uploaded_files[0]["path_in_repo"])


if __name__ == "__main__":
    unittest.main()
