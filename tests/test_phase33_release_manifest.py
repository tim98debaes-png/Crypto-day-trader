"""Phase 33 release-manifest smoke checks."""

from pathlib import Path


REQUIRED_RUNTIME_MODULES = (
    "app.py",
    "phase32_dashboard.py",
    "phase32_streamlit_dashboard.py",
    "phase32_app_adapter.py",
)


def test_release_runtime_modules_are_present():
    root = Path(__file__).resolve().parents[1]
    missing = [name for name in REQUIRED_RUNTIME_MODULES if not (root / name).is_file()]
    assert not missing, f"Missing release runtime modules: {missing}"


def test_temporary_phase32_ci_trigger_is_removed():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "PHASE32_CI_TRIGGER.md").exists()
