import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from dateutil import tz

from pyvodb.load import get_db, load_from_directory
from pyvodb.tables import Series

CET = tz.gettz('Europe/Prague')

def test_recurrence(db):
    query = db.query(Series)
    query = query.filter(Series.slug == 'brno-pyvo')
    series = query.one()
    next_occurences = series.next_occurrences(
        since=datetime.date(2017, 8, 15),
        n=5,
    )
    assert list(next_occurences) == [
        datetime.datetime(2017, 8, 31, 19, tzinfo=CET),
        datetime.datetime(2017, 9, 28, 19, tzinfo=CET),
        datetime.datetime(2017, 10, 26, 19, tzinfo=CET),
        datetime.datetime(2017, 11, 30, 19, tzinfo=CET),
        datetime.datetime(2017, 12, 28, 19, tzinfo=CET),
    ]
    assert series.recurrence_description_cs == (
        'Brněnské Pyvo bývá každý poslední čtvrtek v měsíci.')

def test_recurrence_monthly(db):
    """Test the case where Pyvo already took place that month, but at a
    non-traditional date.
    Future meetup dates should not include that month.
    """
    query = db.query(Series)
    query = query.filter(Series.slug == 'brno-pyvo-rruletest')
    series = query.one()
    next_occurences = series.next_occurrences(
        since=datetime.date(2012, 11, 15),
        n=2,
    )
    assert list(next_occurences) == [
        datetime.datetime(2012, 12, 27, 19, tzinfo=CET),
        datetime.datetime(2013, 1, 31, 19, tzinfo=CET),
    ]

def test_recurrence_after(db):
    """Test that meetup dates are only predicted after the last event.
    """
    query = db.query(Series)
    query = query.filter(Series.slug == 'brno-pyvo-rruletest')
    series = query.one()
    next_occurences = series.next_occurrences(
        since=datetime.date(1999, 1, 1),
        n=2,
    )
    assert list(next_occurences) == [
        datetime.datetime(2012, 12, 27, 19, tzinfo=CET),
        datetime.datetime(2013, 1, 31, 19, tzinfo=CET),
    ]

def test_no_recurrence(db):
    query = db.query(Series)
    query = query.filter(Series.slug == 'praha-pyvo')
    # In the test data, recurrence info for praha-pyvo is missing
    series = query.one()
    next_occurences = series.next_occurrences(
        since=datetime.date(2017, 8, 1),
        n=5,
    )
    assert list(next_occurences) == []
