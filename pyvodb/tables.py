import re
from urllib.parse import urlparse
import datetime

from sqlalchemy import Column, ForeignKey, MetaData, extract, desc
from sqlalchemy.types import Boolean, Integer, Unicode, UnicodeText, Date, Time
from sqlalchemy.types import Numeric, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref, relationship
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.ext.associationproxy import association_proxy
import unidecode
from dateutil import tz

metadata = MetaData()
TableBase = declarative_base(metadata=metadata)

CET = tz.gettz('Europe/Prague')

def date_property(name):
    @hybrid_property
    def _func(self):
        return getattr(self.date, name)
    @_func.expression
    def _func(self):
        return extract(name, self.date)
    return _func


def slugify(name):
    """Make a filename-friendly approximation of a string

    The result only uses the characters a-z, 0-9, _, -
    """
    decoded = unidecode.unidecode(name).lower()
    return re.sub('[^a-z0-9_]+', '-', decoded).strip('-')


class Event(TableBase):
    u"""An event."""
    __tablename__ = 'events'
    id = Column(
        Integer, primary_key=True, nullable=False,
        doc=u"An internal numeric ID")
    name = Column(
        Unicode(), nullable=False,
        doc=u"General name of the event")
    number = Column(
        Integer(), nullable=True,
        doc=u"Serial number of the event (if kept track of)")
    topic = Column(
        Unicode(), nullable=True,
        doc=u"Topic of the event")
    description = Column(
        UnicodeText(), nullable=True,
        doc=u"Description of the event")
    date = Column(
        Date(),
        doc=u"Day the event takes place")
    start_time = Column(
        Time(),
        doc=u"The start time")
    city_id = Column(ForeignKey('cities.id'), nullable=False)
    city = relationship('City', backref=backref('events',
                                                order_by=desc('date')))
    venue_id = Column(ForeignKey('venues.id'), nullable=False)
    venue = relationship('Venue', backref=backref('events'))
    talks = relationship('Talk', collection_class=ordering_list('index'),
                         order_by='Talk.index',
                         backref=backref('event'))

    @property
    def title(self):
        parts = [self.name]
        if self.number is not None:
            parts.append('#{}'.format(self.number))
        elif self.topic:
            parts.append('–')
        if self.topic:
            parts.append(self.topic)
        return ' '.join(parts)

    @property
    def start(self):
        """The event's start time, as a timezone-aware datetime object"""
        if self.start_time is None:
            time = datetime.time(hour=19, tzinfo=CET)
        else:
            time = self.start_time.replace(tzinfo=CET)
        return datetime.datetime.combine(self.date, time)

    year = date_property('year')
    month = date_property('month')
    day = date_property('day')

    @classmethod
    def from_dict(cls, info, db=None):
        self = cls(
            name=info['name'],
            number=info.get('number'),
            topic=info.get('topic'),
            description=info.get('description'),
            date=info.get('start'),
            city=City.get_or_make(info['city'], db),
            venue=Venue.get_or_make(info['venue'], db),
        )
        assert self.city.name == info['city']
        if hasattr(info.get('start'), 'time'):
            self.start_time = info.get('start').time()
        for url in info.get('urls', []):
            self.links.append(EventLink(url=url))
        self.talks = [Talk.from_dict(d, i, db)
                      for i, d in enumerate(info['talks'])]
        return self


class City(TableBase):
    u"""A city that holds events"""
    __tablename__ = 'cities'
    id = Column(
        Integer, primary_key=True, nullable=False,
        doc=u"An internal numeric ID")
    name = Column(
        Unicode(), nullable=False,
        doc=u"Name of the city")
    slug = Column(
        Unicode(), nullable=False, unique=True,
        doc=u"Unique identifier for use in URLs")

    @classmethod
    def get_or_make(cls, name, db=None):
        if db is not None:
            query = db.query(City).filter(City.name == name)
            try:
                return query.one()
            except NoResultFound:
                pass
        return cls(
            name=name,
            slug=slugify(name),
        )


class Venue(TableBase):
    u"""A venue to old events in"""
    __tablename__ = 'venues'
    id = Column(
        Integer, primary_key=True, nullable=False,
        doc=u"An internal numeric ID")
    name = Column(
        Unicode(), nullable=False,
        doc=u"Name of the venue")
    city = Column(
        Unicode(), nullable=False,
        doc=u"City of the venue")
    address = Column(
        Unicode(), nullable=True,
        doc=u"Address of the venue")
    longitude = Column(
        Numeric(), nullable=False,
        doc=u"Longitude of the location")
    latitude = Column(
        Numeric(), nullable=False,
        doc=u"Latitude of the location")
    slug = Column(
        Unicode(), nullable=False, unique=True,
        doc=u"Unique identifier for use in URLs")

    @classmethod
    def get_or_make(cls, info, db=None):
        if db is not None:
            query = db.query(Venue).filter(Venue.name == info['name'])
            try:
                venue = query.one()
            except NoResultFound:
                pass
            else:
                assert venue.name == info['name']
                assert venue.city == info['city']
                # XXX: Address pulled from Lanyrd is unreliable
                assert venue.longitude == info['location']['longitude']
                assert venue.latitude == info['location']['latitude']
                return venue
        return cls(
            name=info['name'],
            city=info['city'],
            address=info.get('address'),
            longitude=info['location']['longitude'],
            latitude=info['location']['latitude'],
            slug=slugify(info['name']),
        )

    @property
    def short_address(self):
        if self.address is not None:
            return self.address.splitlines()[0]


class EventLink(TableBase):
    __tablename__ = 'event_links'
    event_id = Column(ForeignKey('events.id'), primary_key=True, nullable=False)
    event = relationship('Event', backref=backref('links'))
    url = Column(Unicode(), primary_key=True, nullable=False)


class Talk(TableBase):
    u"""A talk"""
    __tablename__ = 'talks'
    id = Column(
        Integer, primary_key=True, nullable=False,
        doc=u"An internal numeric ID")
    title = Column(
        Unicode(), nullable=False,
        doc=u"Talk title")
    index = Column(
        Integer(), nullable=False,
        doc=u"Index in order of talks within an event")
    is_lightning = Column(
        Boolean(), nullable=False, default=False,
        doc=u"True if this is a lightning talk")
    event_id = Column(ForeignKey('events.id'), nullable=True)
    talk_speakers = relationship('TalkSpeaker',
                                 collection_class=ordering_list('index'),
                                 order_by='TalkSpeaker.index',
                                 backref=backref('talk'))
    speakers = association_proxy('talk_speakers', 'speaker',
                                 creator=lambda s: TalkSpeaker(speaker=s))
    links = relationship('TalkLink',
                         collection_class=ordering_list('index'),
                         order_by='TalkLink.index',
                         backref=backref('talk'))

    @classmethod
    def from_dict(cls, info, index, db=None):
        self = cls(
            title=info['title'],
            index=index,
            is_lightning=info.get('lightning'),
        )
        if db:
            db.add(self)
        self.speakers = [Speaker.get_or_make(name, db)
                         for name in info.get('speakers', [])]
        for url in info['urls']:
            self.links.append(TalkLink(url=url, kind='talk'))
        for coverage in info['coverage']:
            for kind, url in coverage.items():
                self.links.append(TalkLink(url=url, kind=kind))
        return self


class Speaker(TableBase):
    __tablename__ = 'speakers'
    id = Column(
        Integer, primary_key=True, nullable=False,
        doc=u"An internal numeric ID")
    name = Column(
        Unicode(), nullable=False,
        doc=u"Name of the venue")
    talk_speakers = relationship('TalkSpeaker', backref=backref('speaker'))
    talks = association_proxy('talk_speakers', 'talk',
                              creator=lambda t: TalkSpeaker(talk=t))

    @classmethod
    def get_or_make(cls, name, db=None):
        if db is not None:
            query = db.query(Speaker).filter(Speaker.name == name)
            try:
                return query.one()
            except NoResultFound:
                pass
        return cls(
            name=name,
        )


class TalkSpeaker(TableBase):
    __tablename__ = 'talk_speakers'
    talk_id = Column(ForeignKey('talks.id'), primary_key=True, nullable=False)
    speaker_id = Column(ForeignKey('speakers.id'), primary_key=True, nullable=False)
    index = Column(
        Integer(), nullable=True,
        doc=u"Index in order of a talk's speakers")


class TalkLink(TableBase):
    __tablename__ = 'talk_links'
    talk_id = Column(ForeignKey('talks.id'), primary_key=True, nullable=False)
    url = Column(Unicode(), primary_key=True, nullable=False)
    index = Column(
        Integer(),
        doc=u"Index in order of a talk's speakers")
    kind = Column(
        Enum('slides', 'video', 'link', 'writeup', 'notes', 'talk'),
        doc="Kind of the link. 'talk' is a link to the talk itself; "
            "the rest is for suporting material")

    @property
    def hostname(self):
        return urlparse(self.url).hostname
