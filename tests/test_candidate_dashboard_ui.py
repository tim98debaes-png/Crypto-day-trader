from pathlib import Path


def test_candidate_registry_streamlit_page_exists_and_is_read_only():
    page = Path("pages/20_Candidate_Registry.py").read_text(encoding="utf-8")
    assert "build_candidate_dashboard" in page
    assert "build_candidate_rows" in page
    assert "promote(" not in page
    assert "rollback(" not in page
    assert "st.dataframe" in page
