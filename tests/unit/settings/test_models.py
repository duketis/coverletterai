"""``RuntimeSettings`` subclass shape."""

from __future__ import annotations

from tailor_core.settings.models import BaseRuntimeSettings

from coverletterai.settings.models import RuntimeSettings


def test_runtime_settings_subclasses_base() -> None:
    assert issubclass(RuntimeSettings, BaseRuntimeSettings)


def test_runtime_settings_inherits_model_field() -> None:
    """``model`` (LLM override) is the only shared key on the base; the
    coverletterai subclass adds no fields in v0.1."""
    settings = RuntimeSettings()
    assert settings.model is None


def test_runtime_settings_accepts_explicit_model() -> None:
    settings = RuntimeSettings(model="claude-sonnet-4-6")
    assert settings.model == "claude-sonnet-4-6"


def test_runtime_settings_round_trips() -> None:
    settings = RuntimeSettings(model="claude-opus-4-7")
    assert RuntimeSettings.model_validate_json(settings.model_dump_json()) == settings


def test_runtime_settings_is_frozen() -> None:
    """``ConfigDict(frozen=True)`` is inherited from BaseRuntimeSettings."""
    import pydantic  # noqa: PLC0415

    settings = RuntimeSettings()
    try:
        settings.model = "tampered"
    except pydantic.ValidationError:
        return
    raise AssertionError("frozen settings should reject reassignment")
