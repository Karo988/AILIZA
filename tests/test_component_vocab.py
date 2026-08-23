from apps.backend import component_vocab as vocab


def test_every_transition_references_known_states():
    known = set(vocab.COMPONENT_STATES)
    assert len(known) == len(vocab.COMPONENT_STATES)
    for source, target in vocab.ALLOWED_COMPONENT_TRANSITIONS:
        assert source in known
        assert target in known


def test_every_state_is_represented_in_transition_table():
    represented = {
        state
        for transition in vocab.ALLOWED_COMPONENT_TRANSITIONS
        for state in transition
    }
    assert represented == set(vocab.COMPONENT_STATES)


def test_no_activation_without_approval_and_purged_is_terminal():
    transitions = vocab.ALLOWED_COMPONENT_TRANSITIONS
    assert (vocab.APPROVED, vocab.ACTIVE) in transitions
    assert all(
        source in {vocab.APPROVED, vocab.DEGRADED}
        for source, target in transitions
        if target == vocab.ACTIVE
    )
    assert all(source != vocab.PURGED for source, _target in transitions)


def test_explicit_permissions_and_scopes_are_unique():
    assert len(vocab.COMPONENT_PERMISSIONS) == 11
    assert vocab.MEMORY_SCOPES == {"session", "personal", "project", "company"}
