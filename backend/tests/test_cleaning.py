from datetime import date, timedelta

from app.importers.cleaning import clean_weights


def _series(values, start=date(2026, 1, 1)):
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


def test_keeps_normal_series():
    kept, rep = clean_weights(_series([80.0, 79.8, 79.9, 79.6, 79.5, 79.7]))
    assert len(kept) == 6
    assert rep.placeholders == [] and rep.outliers == [] and rep.out_of_range == 0


def test_removes_repeated_placeholder():
    values = [81.0, 78.2, 81.0, 78.0, 81.0, 77.9, 81.0, 77.8, 81.0, 77.7]
    kept, rep = clean_weights(_series(values))
    assert 81.0 in rep.placeholders
    assert all(round(w, 2) != 81.0 for _, w in kept)
    assert len(kept) == 5


def test_removes_out_of_range():
    kept, rep = clean_weights(_series([80.0, 0.0, 79.5, 500.0, 79.4]))
    assert rep.out_of_range == 2
    assert len(kept) == 3


def test_removes_single_outlier():
    values = [80.0, 79.9, 80.1, 80.0, 60.5, 79.8, 80.0, 79.9, 80.2]
    kept, rep = clean_weights(_series(values))
    assert [w for _, w in rep.outliers] == [60.5]
    assert len(kept) == len(values) - 1


def test_empty():
    kept, rep = clean_weights([])
    assert kept == [] and rep.raw == 0
