from sqlalchemy import Column, ForeignKey, MetaData, PrimaryKeyConstraint, Table, UniqueConstraint
from sqlalchemy.types import Boolean, Integer, Unicode, UnicodeText
from sqlalchemy.ext.declarative import declarative_base

metadata = MetaData()
TableBase = declarative_base(metadata=metadata)

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
    # XXX: Series
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
