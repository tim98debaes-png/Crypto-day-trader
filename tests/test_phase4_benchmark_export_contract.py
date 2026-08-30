from research.phase4_benchmark_export import main

def test_phase4_cli_entrypoint_exists():
    assert callable(main)
