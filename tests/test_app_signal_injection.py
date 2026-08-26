from pathlib import Path


def test_app_contains_injection_target_and_signal_adapter():
    app = Path("app.py").read_text(encoding="utf-8")
    patch = Path("scripts/integrate_paper_signals.py").read_text(encoding="utf-8")
    assert 'from signal_engine import generate_signal' in patch
    assert 'raw_signal = "LONG"' in patch
    assert 'signal_result = generate_signal(' in app


def test_injection_patch_is_deterministic_and_narrow():
    patch = Path("scripts/integrate_paper_signals.py").read_text(encoding="utf-8")
    assert patch.count('text.replace(OLD, NEW, 1)') == 1
    assert 'expected live-scanner signal block not found' in patch
