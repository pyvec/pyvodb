import os
import pytest

from pyvo.load import get_db
from pyvo.tables import Event, City, Venue

@pytest.fixture(scope='module')
def db():
    directory = os.path.join(os.path.dirname(__file__), 'data')
    return get_db(directory)

def test_load(db):
    assert db
    assert db.query(Event).first().name

def test_title_3part(db):
    """Test title with name, number, and topic"""
    query = db.query(Event)
    query = query.filter(Event.name == 'Pražské PyVo')
    query = query.filter(Event.number == 50)
    event = query.one()
    assert event.name == 'Pražské PyVo'
    assert event.number == 50
    assert event.topic == 'anniversary'
    assert event.title == 'Pražské PyVo #50 anniversary'

def test_title_with_number(db):
    """Test title with name and number"""
    query = db.query(Event)
    query = query.filter(Event.name == 'Pražské PyVo')
    query = query.filter(Event.number == 49)
    event = query.one()
    assert event.name == 'Pražské PyVo'
    assert event.number == 49
    assert event.topic is None
    assert event.title == 'Pražské PyVo #49'

def test_title_with_topic(db):
    """Test title with name and topic"""
    query = db.query(Event)
    query = query.filter(Event.name == 'Ostravské Pyvo s Rubači')
    query = query.filter(Event.topic == 'Testovací')
    event = query.one()
    assert event.name == 'Ostravské Pyvo s Rubači'
    assert event.number is None
    assert event.topic == 'Testovací'
    assert event.title == 'Ostravské Pyvo s Rubači – Testovací'

def test_title_bare(db):
    """Test title with name only"""
    query = db.query(Event)
    query = query.filter(Event.name == 'Ostravské KinoPyvo')
    event = query.one()
    assert event.name == 'Ostravské KinoPyvo'
    assert event.number is None
    assert event.topic is None
    assert event.title == 'Ostravské KinoPyvo'

def test_date(db):
    query = db.query(Event)
    query = query.filter(Event.year == 2013)
    query = query.filter(Event.month == 5)
    query = query.filter(Event.day == 30)
    event = query.one()
    assert event.year == event.date.year == 2013
    assert event.month == event.date.month == 5
    assert event.day == event.date.day == 30

def test_time(db):
    query = db.query(Event)
    query = query.filter(Event.year == 2013)
    query = query.filter(Event.month == 5)
    query = query.filter(Event.day == 30)
    event = query.one()
    assert event.start_time is not None
    assert event.start_time.hour == 19
    assert event.start_time.minute == 0
    assert event.start_time.second == 0

def test_no_time(db):
    """Test an event with no start time set"""
    query = db.query(Event)
    query = query.filter(Event.year == 2013)
    query = query.filter(Event.month == 12)
    query = query.filter(Event.day == 4)
    event = query.one()
    assert event.start_time is None

def test_city(db):
    """Test that an event has a city"""
    query = db.query(Event)
    query = query.filter(Event.year == 2013)
    query = query.filter(Event.month == 12)
    query = query.filter(Event.day == 4)
    event = query.one()
    assert event.city.name == 'Ostrava'

def test_cities(db):
    """Test that a city has events"""
    query = db.query(City)
    query = query.filter(City.name == 'Ostrava')
    city = query.one()
    assert city.events
    assert any(e.name == 'Ostravské KinoPyvo' for e in city.events)
    assert not any(e.name == 'Brněnské Pyvo' for e in city.events)

def test_venue(db):
    """Test that an event has a venue"""
    query = db.query(Event)
    query = query.filter(Event.year == 2013)
    query = query.filter(Event.month == 12)
    query = query.filter(Event.day == 4)
    event = query.one()
    assert event.venue.name == 'Sport Club'

def test_venues(db):
    """Test that a venue has events"""
    query = db.query(Venue)
    query = query.filter(Venue.name == 'Na Věnečku')
    query = query.filter(Venue.city == 'Prague')
    venue = query.one()
    assert venue.events
    assert any(e.name == 'Pražské PyVo' for e in venue.events)
    assert not any(e.name == 'Brněnské Pyvo' for e in venue.events)

def test_urls(db):
    """Test that an event has URLs"""
    query = db.query(Event)
    query = query.filter(Event.year == 2013)
    query = query.filter(Event.month == 12)
    query = query.filter(Event.day == 4)
    event = query.one()
    [url] = event.urls
    assert url.url == 'http://lanyrd.com/2013/ostravske-pyvo-druhe/'

def test_talk_titles(db):
    """Test that an event has some talks"""
    query = db.query(Event)
    query = query.filter(Event.year == 2015)
    query = query.filter(Event.month == 3)
    query = query.filter(Event.day == 18)
    event = query.one()
    assert [t.title for t in event.talks] == [
        'Docker & Autoscaling',
        'Optimalizace v Pythonu',
        'Lightning talk: Django Girls Praha',
        'Lightning Talk: Knihovnička, EuroPython',
        'Lightning talk: Docker Meetup 24. 3.',
        'Lightning talk: PEP 489 draft']
