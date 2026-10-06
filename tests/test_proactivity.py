from companhia.proactivity import Proactivity


def test_opt_in_busy_editing_and_one_unanswered():
    p = Proactivity()
    assert not p.eligible(100, False, False, True)
    p.mode = "company"
    assert not p.eligible(89, False, False, True)
    assert not p.eligible(100, True, False, True)
    assert not p.eligible(100, False, True, True)
    assert not p.eligible(100, False, False, False)
    assert p.eligible(100, False, False, True)
    p.started(100)
    p.delivered()
    assert not p.eligible(800, False, False, True)
    p.activity(801)
    assert not p.eligible(890, False, False, True)
    assert p.eligible(900, False, False, True)
    p.mode = "paused"
    assert not p.eligible(1000, False, False, True)


def test_cooldown_and_hourly_limit():
    p = Proactivity(mode="company", idle_seconds=10)
    p.started(100)
    p.activity(101)
    assert not p.eligible(399, False, False, True)
    assert p.eligible(400, False, False, True)
    for t in [400, 700, 1000]:
        p.started(t)
        p.activity(t + 1)
    assert not p.eligible(1300, False, False, True)
    assert p.eligible(3701, False, False, True)
