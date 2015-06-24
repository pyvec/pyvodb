from sqlalchemy import Column, ForeignKey, MetaData, extract
from sqlalchemy.types import Boolean, Integer, Unicode, UnicodeText, Date, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref, relationship
from sqlalchemy.orm.exc import NoResultFound

metadata = MetaData()
TableBase = declarative_base(metadata=metadata)

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
    desription = Column(
        UnicodeText(), nullable=True,
        doc=u"Description of the event")
    date = Column(
        Date(),
        doc=u"Day the event takes place")
    start_time = Column(
        Time(),
        doc=u"The start time")
    city_id = Column(
        ForeignKey('cities.name'),
        doc=u"ID of the event's city")
    city = relationship('City', backref=backref('events'))
    # XXX: Venue
    # XXX: Talks
    # XXX: URLs

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

    year = date_property('year')
    month = date_property('month')
    day = date_property('day')

    @classmethod
    def from_dict(cls, info, db=None):
        self = cls(
            name=info['name'],
            number=info.get('number'),
            topic=info.get('topic'),
            desription=info.get('desription'),
            date=info.get('start'),
            city=City.get_or_make(info['city'], db),
        )
        assert self.city.name == info['city']
        if hasattr(info.get('start'), 'time'):
            self.start_time = info.get('start').time()
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
        )
