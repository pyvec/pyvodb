import os
import sys
import json
import datetime
import contextlib
import collections

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.expression import select

from . import tables

try:
    YAML_SAFE_LOADER = yaml.CSafeLoader
except AttributeError:
    YAML_SAFE_LOADER = yaml.SafeLoader


def get_db(directory, engine=None):
    """Get a database

    :param directory: The root data directory
    :param engine: a pre-created SQLAlchemy engine (default: in-memory SQLite)
    """
    if engine is None:
        engine = create_engine('sqlite://')
    tables.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    if directory is not None:
        load_from_directory(db, directory)
    return db


def dict_from_directory(directory, root):
    data = {}
    for filename in os.listdir(os.path.join(root, directory)):
        fullname = os.path.join(directory, filename)
        absname = os.path.join(root, fullname)
        if filename in ('.git', 'README') or filename.startswith('.'):
            pass
        elif filename.endswith('.yaml'):
            with open(absname) as f:
                info = yaml.load(f, Loader=YAML_SAFE_LOADER)
            info['_source'] = fullname
            data[filename[:-5]] = info
        elif os.path.isdir(absname):
            data[filename] = dict_from_directory(fullname, root)
        else:
            raise ValueError('Unexpected file: ' + fullname)
    return data


def load_from_directory(db, directory):
    data = dict_from_directory('.', directory)
    load_from_dict(db, data)


def load_from_dict(db, data):
    """Load data from a dict (as loaded from directory of YAMLs) into database
    """
    # The ORM overhead is too high for this kind of bulk load,
    # so drop down to SQLAlchemy Core.
    # This tries to do minimize the number of SQL commands by loading entire
    # tables at once

    if data['meta']['version'] != 2:
        raise ValueError('Can only load version 2')

    if db.get_bind(tables.Event).dialect.name == 'sqlite':
        db.execute('PRAGMA foreign_keys = ON')

    with bulk_inserter(db) as insert:

        # Load speakers

        speaker_slugs = set()

        for series_slug, series in data['series'].items():
            for event_slug, event in series['events'].items():
                for talk in event.get('talks'):
                    for speaker in talk.get('speakers', ()):
                        if speaker not in speaker_slugs:
                            speaker_slugs.add(speaker)
                            insert(tables.Speaker, {
                                'slug': speaker,
                                'name': speaker,
                            })

        venue_ids = {}

        # Load cities, and their venues

        for city_slug, city in data['cities'].items():
            city_data = city['city']
            insert(tables.City, {
                'slug': city_slug,
                'name': city_data['name'],
                'latitude': city_data['location']['latitude'],
                'longitude': city_data['location']['longitude'],
                '_source': city_data['_source'],
            })

            for venue_slug, venue in city.get('venues', {}).items():
                venue_ids[city_slug, venue_slug] = insert(tables.Venue, {
                    'city_slug': city_slug,
                    'slug': venue_slug,
                    'name': venue['name'],
                    'address': venue['address'],
                    'latitude': venue['location']['latitude'],
                    'longitude': venue['location']['longitude'],
                })


        # Load series, their events, and everything underneath

        for series_slug, series_dir in data['series'].items():

            series = series_dir['series']
            recurrence = series.get('recurrence')
            if 'recurrence' in series:
                recurrence_attrs = {
                    'recurrence_rule': recurrence['rrule'],
                    'recurrence_scheme': recurrence['scheme'],
                    'recurrence_description_cs': recurrence['description']['cs'],
                    'recurrence_description_en': recurrence['description']['en'],
                }
            else:
                recurrence_attrs = {}
            insert(tables.Series, {
                'slug': series_slug,
                'name': series['name'],
                'home_city_slug': series.get('city'),
                'description_cs': series['description']['cs'],
                'description_en': series['description']['en'],
                'organizer_info': json.dumps(series['organizer-info']),
                **recurrence_attrs,
            })

            for event_slug, event in series_dir['events'].items():
                venue_slug = event.get('venue')
                city_slug = event['city']
                if venue_slug:
                    venue_id = venue_ids[city_slug, venue_slug]
                else:
                    venue_id = None

                start = make_full_datetime(event['start'])
                event_id = insert(tables.Event, {
                    'name': event['name'],
                    'number': event.get('number'),
                    'topic': event.get('topic'),
                    'description': event.get('description'),
                    'date': start.date(),
                    'start_time': start.time(),
                    'series_slug': series_slug,
                    'city_slug': city_slug,
                    'venue_id': venue_id,
                    '_source': event['_source']
                })

                for i, talk in enumerate(event.get('talks', ())):
                    talk_id = insert(tables.Talk, {
                        'event_id': event_id,
                        'index': i,
                        'title': talk['title'],
                        'description': talk.get('description'),
                        'is_lightning': talk.get('lightning', False),
                    })

                    for i, speaker in enumerate(talk.get('speakers', ())):
                        assert speaker in speaker_slugs
                        insert(tables.TalkSpeaker, {
                            'talk_id': talk_id,
                            'index': i,
                            'speaker_slug': speaker,
                        })

                    for i, link in enumerate([
                            *({'talk': u} for u in talk.get('urls', ())),
                            *talk.get('coverage', {})]):
                        for kind, url in link.items():
                            insert(tables.TalkLink, {
                                'talk_id': talk_id,
                                'index': i,
                                'url': url,
                                'kind': kind,
                            })

                for i, url in enumerate(event.get('urls', ())):
                    insert(tables.EventLink, {
                        'event_id': event_id,
                        'index': i,
                        'url': url,
                    })


def make_full_datetime(value):
    if hasattr(value, 'time'):
        date = value.date()
        time = value.time()
    else:
        date = value
        time = datetime.time(hour=19)
    return datetime.datetime.combine(date, time)


@contextlib.contextmanager
def bulk_inserter(db):
    next_id = {}
    table_columns = {}
    table_rows = collections.OrderedDict()
    need_id = {}

    def insert(orm_class, row):
        table = orm_class.__table__
        if table in table_columns:
            if set(row) != table_columns[table]:
                raise ValueError('uneven table row')
        else:
            next_id[table] = 0
            table_columns[table] = set(row)
            table_rows[table] = []
            need_id[table] = ('id' in table.c and table.c['id'].autoincrement)

        row = dict(row)
        if need_id[table]:
            row['id'] = the_id = next_id[table]
            next_id[table] += 1
        else:
            the_id = None

        table_rows[table].append(row)

        return the_id

    yield insert

    for table, rows in table_rows.items():
        db.execute(table.insert(), rows)
