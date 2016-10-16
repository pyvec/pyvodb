import re
from urllib.parse import urlparse
import datetime
import collections
import itertools

from sqlalchemy import Column, ForeignKey, MetaData, extract, desc
from sqlalchemy import UniqueConstraint
from sqlalchemy.types import Boolean, Integer, Unicode, UnicodeText, Date, Time
from sqlalchemy.types import Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref, relationship
from sqlalchemy.orm.session import Session
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.ext.associationproxy import association_proxy
from dateutil import tz, rrule, relativedelta

metadata = MetaData()
TableBase = declarative_base(metadata=metadata)

CET = tz.gettz('Europe/Prague')

YOUTUBE_RE = re.compile('https?://www.youtube.com/watch\?v=([-0-9a-zA-Z_]+)')


def date_property(name):
    @hybrid_property
    def _func(self):
        return getattr(self.date, name)
    @_func.expression
    def _func(self):
        return extract(name, self.date)
    return _func


class Event(TableBase):
    u"""An event."""
    __tablename__ = 'events'
    __table_args__ = (UniqueConstraint('city_slug', 'date', 'start_time'),)
    id = Column(
        Integer, primary_key=True, nullable=False,
        doc=u"An internal numeric ID")
    series_slug = Column(
        ForeignKey('series.slug'), nullable=False,
        doc=u"The series this event belongs to")
    name = Column(
        Unicode(), nullable=False,
        doc=u"General name of the event – often, this is the same as the "
            u"name of the series")
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
    _source = Column(
        Unicode(), nullable=True,
        doc=u"File from which the entry was loaded")
    city_slug = Column(ForeignKey('cities.slug'), nullable=False)
    city = relationship('City', backref=backref('events',
                                                order_by=desc('date')))
    series = relationship('Series', backref=backref('events',
                                                    order_by=desc('date')))
    venue_id = Column(ForeignKey('venues.id'), nullable=True)
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

    def as_dict(self):
        talks = []
        for talk in self.talks:
            talk_info = collections.OrderedDict()
            talks.append(talk_info)
            talk_info['title'] = talk.title
            if talk.is_lightning:
                talk_info['lightning'] = True
            talk_info['speakers'] = [s.name for s in talk.speakers]
            talk_info['urls'] = [l.url for l in talk.links if l.kind == 'talk']
            talk_info['coverage'] = [{l.kind: l.url} for l in talk.links if l.kind != 'talk']
            if talk.description:
                talk_info['description'] = talk.description

        result = collections.OrderedDict()
        result['city'] = self.city.slug
        result['start'] = datetime.datetime.combine(self.date, self.start_time)
        result['name'] = self.name
        if self.number is not None:
            result['number'] = self.number
        if self.topic is not None:
            result['topic'] = self.topic
        if self.description is not None:
            result['description'] = self.description
        if self.venue:
            result['venue'] = self.venue.slug
        result['talks'] = talks
        result['urls'] = [l.url for l in self.links]
        return result


class City(TableBase):
    u"""A city that holds events"""
    __tablename__ = 'cities'
    slug = Column(
        Unicode(), primary_key=True,
        doc=u"Unique identifier for use in URLs")
    name = Column(
        Unicode(), nullable=False,
        doc=u"Name of the city")
    longitude = Column(
        Unicode(), nullable=False,
        doc=u"Longitude of the location")
    latitude = Column(
        Unicode(), nullable=False,
        doc=u"Latitude of the location")
    _source = Column(
        Unicode(), nullable=True,
        doc=u"File from which the entry was loaded")


class Series(TableBase):
    u"""A series events"""
    __tablename__ = 'series'
    slug = Column(
        Unicode(), primary_key=True,
        doc=u"Unique identifier for use in URLs")
    name = Column(
        Unicode(), nullable=False,
        doc=u"Name of the series")
    home_city_slug = Column(
        ForeignKey(City.slug), nullable=True,
        doc=u"City this series usually takes place at, if any")
    description_cs = Column(
        Unicode(), nullable=True,
        doc=u"Czech description")
    description_en = Column(
        Unicode(), nullable=True,
        doc=u"English description")

    recurrence_scheme = Column(
        Unicode(), nullable=True,
        doc=u"Basic type of the series' recurrence scheme")
    recurrence_rule = Column(
        Unicode(), nullable=True,
        doc=u"RFC 2445 recurrence rule for regular event dates")
    recurrence_description_cs = Column(
        Unicode(), nullable=True,
        doc=u"Czech description of the recurrence rule")
    recurrence_description_cs = Column(
        Unicode(), nullable=True,
        doc=u"English description of the recurrence rule")

    # XXX: Remove this:
    organizer_info = Column(
        Unicode(), nullable=True,
        doc=u"Info about organizers, as JSON.")

    home_city = relationship('City', backref=backref('series'))

    def next_occurrences(self, n=None, since=None):
        """Yield the next planned occurrences after the date "since"

        The `since` argument can be either a date or datetime onject.
        If not given, it defaults to the date of the last event that's
        already planned.

        If `n` is given, the result is limited to that many dates;
        otherwise, infinite results may be generated.
        Note that less than `n` results may be yielded.
        """
        scheme = self.recurrence_scheme
        if scheme is None:
            return ()

        if since is None:
            db = Session.object_session(self)
            query = db.query(Event)
            query = query.filter(Event.series_slug == self.slug)
            query = query.order_by(desc(Event.date))
            query = query.limit(1)
            last_planned_event = query.one()
            since = last_planned_event.date

        start = getattr(since, 'date', since)
        if scheme == 'monthly':
            # Monthly events try to have one event per month, so start
            # on the 1st of next month
            print(start)
            start += relativedelta.relativedelta(months=+1)
            start = start.replace(day=1)
        else:
            raise ValueError('Unknown recurrence scheme: ' + scheme)
        result = rrule.rrulestr(self.recurrence_rule, dtstart=start)
        if n is not None:
            result = itertools.islice(result, n)
        return result


class Venue(TableBase):
    u"""A venue to old events in"""
    __tablename__ = 'venues'
    __table_args__ = (UniqueConstraint('city_slug', 'slug'),)
    id = Column(
        Integer, primary_key=True, nullable=False,
        doc=u"An internal numeric ID")
    name = Column(
        Unicode(), nullable=False,
        doc=u"Name of the venue")
    city_slug = Column(
        ForeignKey('cities.slug'), nullable=False,
        doc=u"City of the venue")
    address = Column(
        Unicode(), nullable=True,
        doc=u"Address of the venue")
    longitude = Column(
        Unicode(), nullable=False,
        doc=u"Longitude of the location")
    latitude = Column(
        Unicode(), nullable=False,
        doc=u"Latitude of the location")
    slug = Column(
        Unicode(), nullable=False,
        doc=u"Identifier for use in URLs")

    city = relationship('City', backref=backref('venues'))

    @property
    def short_address(self):
        if self.address is not None:
            return self.address.splitlines()[0]


class EventLink(TableBase):
    __tablename__ = 'event_links'
    event_id = Column(ForeignKey('events.id'), primary_key=True, nullable=False)
    event = relationship('Event', backref=backref('links', cascade='delete'))
    url = Column(Unicode(), primary_key=True, nullable=False)
    index = Column(
        Integer(),
        doc=u"Index in order of an event's links")


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
    description = Column(
        UnicodeText(), nullable=True,
        doc=u"Description of the talk")
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

    @property
    def youtube_id(self):
        for link in self.links:
            yid = link.youtube_id
            if yid:
                return yid


class Speaker(TableBase):
    __tablename__ = 'speakers'
    slug = Column(
        Unicode(), primary_key=True,
        doc=u"Slug to be used in URLs")
    name = Column(
        Unicode(), nullable=False,
        doc=u"Name of the speaker")
    talk_speakers = relationship('TalkSpeaker', backref=backref('speaker'))
    talks = association_proxy('talk_speakers', 'talk',
                              creator=lambda t: TalkSpeaker(talk=t))


class TalkSpeaker(TableBase):
    __tablename__ = 'talk_speakers'
    talk_id = Column(
        ForeignKey('talks.id'),
        primary_key=True, nullable=False)
    speaker_slug = Column(
        ForeignKey('speakers.slug'),
        primary_key=True, nullable=False)
    index = Column(
        Integer(), nullable=True,
        doc=u"Index in order of a talk's speakers")


class TalkLink(TableBase):
    __tablename__ = 'talk_links'
    talk_id = Column(
        ForeignKey('talks.id'), primary_key=True, nullable=False)
    url = Column(Unicode(), primary_key=True, nullable=False)
    index = Column(
        Integer(),
        doc=u"Index in order of a talk's links")
    kind = Column(
        Enum('slides', 'video', 'link', 'writeup', 'notes', 'talk'),
        doc="Kind of the link. 'talk' is a link to the talk itself; "
            "the rest is for suporting material")

    @property
    def hostname(self):
        return urlparse(self.url).hostname

    @property
    def youtube_id(self):
        match = YOUTUBE_RE.match(self.url)
        if match:
            return match.group(1)
