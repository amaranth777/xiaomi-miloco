"""Tests for perception engine resource validation."""

from miloco.perception.engine.resource_validator import (
    MODELS,
    EngineReadiness,
    validate_resources,
)


def _create_all_models(tmp_path):
    for m in MODELS:
        (tmp_path / m.name).write_bytes(b"\x00")


class TestValidateResources:
    def test_all_resources_available(self, tmp_path):
        _create_all_models(tmp_path)
        result = validate_resources("test-key", str(tmp_path))
        assert result.status == EngineReadiness.READY
        assert result.missing_models == []

    def test_missing_api_key(self, tmp_path):
        _create_all_models(tmp_path)
        result = validate_resources("", str(tmp_path))
        assert result.status == EngineReadiness.NOT_CONFIGURED
        assert "API Key" in result.message

    def test_missing_models_dir_none(self):
        result = validate_resources("test-key", None)
        assert result.status == EngineReadiness.MODELS_MISSING

    def test_missing_models_dir_empty(self):
        result = validate_resources("test-key", "")
        assert result.status == EngineReadiness.MODELS_MISSING

    def test_models_dir_not_exists_is_created(self, tmp_path):
        new_dir = tmp_path / "new_models"
        result = validate_resources("test-key", str(new_dir))
        assert result.status == EngineReadiness.MODELS_MISSING
        assert new_dir.is_dir()

    def test_valid_models_dir_symlink(self, tmp_path):
        target = tmp_path / "real_models"
        target.mkdir()
        _create_all_models(target)
        link = tmp_path / "models_link"
        link.symlink_to(target, target_is_directory=True)

        result = validate_resources("test-key", str(link))
        assert result.status == EngineReadiness.READY

    def test_broken_models_dir_symlink_is_not_replaced(self, tmp_path):
        link = tmp_path / "broken_models_link"
        link.symlink_to(tmp_path / "missing-target", target_is_directory=True)

        result = validate_resources("test-key", str(link))
        assert result.status == EngineReadiness.MODELS_MISSING
        assert link.is_symlink()

    def test_models_path_file_is_not_replaced(self, tmp_path):
        path = tmp_path / "models-file"
        path.write_text("not a directory")

        result = validate_resources("test-key", str(path))
        assert result.status == EngineReadiness.MODELS_MISSING
        assert path.is_file()

    def test_single_model_missing(self, tmp_path):
        _create_all_models(tmp_path)
        (tmp_path / "det_4C.onnx").unlink()

        result = validate_resources("test-key", str(tmp_path))
        assert result.status == EngineReadiness.MODELS_MISSING
        assert "det_4C.onnx" in result.missing_models

    def test_all_models_missing(self, tmp_path):
        result = validate_resources("test-key", str(tmp_path))
        assert result.status == EngineReadiness.MODELS_MISSING
        # 必选模型全部缺失
        assert len(result.missing_models) == 2
        assert "det_4C.onnx" in result.missing_models
        assert "human_body_reid_v2.onnx" in result.missing_models
        # 可选模型在单独字段（bge 句向量 onnx/tokenizer + silero VAD）
        assert result.missing_optional_models == [
            "bge-small-zh-v1.5-int8.onnx",
            "bge-small-zh-v1.5-tokenizer.json",
            "silero_vad.onnx",
        ]
