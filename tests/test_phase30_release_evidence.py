from phase30_release_evidence import release_evidence


def test_release_evidence_has_required_keys():
    evidence = release_evidence()
    assert evidence.keys() == {"required_tests_present", "secrets_absent", "live_disabled"}


def test_current_checkout_has_safe_release_evidence():
    evidence = release_evidence()
    assert evidence["required_tests_present"] is True
    assert evidence["secrets_absent"] is True
    assert evidence["live_disabled"] is True
