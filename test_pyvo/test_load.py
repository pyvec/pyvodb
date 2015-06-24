import pytest

from pyvo.load import get_db
from pyvo.tables import Event

@pytest.fixture(scope='module')
def db():
    return get_db()

def test_load(db):
    assert db
    assert db.query(Event).first().name

def test_title_3part(db):
    """Test title with name, number, and topic"""
    query = db.query(Event)
    query = query.filter(Event.name == 'Pražské PyVo')
    query = query.filter(Event.number == 50)
    event = query.first()
    assert event.name == 'Pražské PyVo'
    assert event.number == 50
    assert event.topic == 'anniversary'
    assert event.title == 'Pražské PyVo #50 anniversary'

def test_title_with_number(db):
    """Test title with name and number"""
    query = db.query(Event)
    query = query.filter(Event.name == 'Pražské PyVo')
    query = query.filter(Event.number == 49)
    event = query.first()
    assert event.name == 'Pražské PyVo'
    assert event.number == 49
    assert event.topic is None
    assert event.title == 'Pražské PyVo #49'

def test_title_with_topic(db):
    """Test title with name and topic"""
    query = db.query(Event)
    query = query.filter(Event.name == 'Ostravské Pyvo s Rubači')
    query = query.filter(Event.topic == 'Testovací')
    event = query.first()
    assert event.name == 'Ostravské Pyvo s Rubači'
    assert event.number is None
    assert event.topic == 'Testovací'
    assert event.title == 'Ostravské Pyvo s Rubači – Testovací'

def test_title_bare(db):
    """Test title with name only"""
    query = db.query(Event)
    query = query.filter(Event.name == 'Ostravské KinoPyvo')
    event = query.first()
    assert event.name == 'Ostravské KinoPyvo'
    assert event.number is None
    assert event.topic is None
    assert event.title == 'Ostravské KinoPyvo'
