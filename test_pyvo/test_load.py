import pytest

from pyvo.load import get_db
from pyvo.tables import Event

@pytest.fixture(scope='module')
def db():
    return get_db()

def test_load(db):
    assert db
    assert db.query(Event).first().name

def test_title_1(db):
    query = db.query(Event)
    query = query.filter(Event.name == 'Pražské PyVo')
    query = query.filter(Event.number == 50)
    event = query.first()
    assert event.name == 'Pražské PyVo'
    assert event.number == 50
    assert event.topic == 'anniversary'
    assert event.title == 'Pražské PyVo #50 anniversary'
