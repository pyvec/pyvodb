import os
import datetime
import contextlib
import sys

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
    print('Reading YAML', file=sys.stderr)
    data = dict_from_directory('.', directory)
    print('Loading DB', file=sys.stderr)
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

    # Load cities, and their venues

    with contextlib.ExitStack() as stack:
        insert_city, city_slugs = stack.enter_context(bulk_loader(
            db, tables.City, id_column='slug'))

        insert_venue, venue_ids = stack.enter_context(bulk_loader(
            db, tables.Venue, key_columns=['city_slug', 'slug']))

        for city_slug, city in data['cities'].items():
            city_data = city['city']
            insert_city({
                'slug': city_slug,
                'name': city_data['name'],
                'latitude': city_data['location']['latitude'],
                'longitude': city_data['location']['longitude'],
                '_source': city_data['_source'],
            })

            for venue_slug, venue in city.get('venues', {}).items():
                insert_venue({
                    'city_slug': city_slug,
                    'slug': venue_slug,
                    'name': venue['name'],
                    'address': venue['address'],
                    'latitude': venue['location']['latitude'],
                    'longitude': venue['location']['longitude'],
                })

    # Load speakers

    speaker_slugs = set()
    with contextlib.ExitStack() as stack:
        insert, speaker_ids = stack.enter_context(bulk_loader(
            db, tables.Speaker, id_column='slug'))

        for series_slug, series in data['series'].items():
            for event_slug, event in series['events'].items():
                for talk in event.get('talks'):
                    for speaker in talk.get('speakers', ()):
                        if speaker not in speaker_slugs:
                            speaker_slugs.add(speaker)
                            insert({
                                'slug': speaker,
                                'name': speaker,
                            })

    # Load events

    with contextlib.ExitStack() as stack:
        insert, event_ids = stack.enter_context(bulk_loader(
            db, tables.Event,
            key_columns=['city_slug', 'date', 'start_time']))

        for series_slug, series in data['series'].items():
            for event_slug, event in series['events'].items():
                venue_slug = event.get('venue')
                city_slug = event['city']
                if venue_slug:
                    venue_id = venue_ids[city_slug, venue_slug]
                else:
                    venue_id = None

                start = make_full_datetime(event['start'])
                insert({
                    'name': event['name'],
                    'number': event.get('number'),
                    'topic': event.get('topic'),
                    'description': event.get('description'),
                    'date': start.date(),
                    'start_time': start.time(),
                    'city_slug': city_slug,
                    'venue_id': venue_id,
                    '_source': event['_source']
                })

    # Load event talks and links

    with contextlib.ExitStack() as stack:
        insert_talk, talk_ids = stack.enter_context(bulk_loader(
            db, tables.Talk,
            key_columns=['event_id', 'index']))

        insert_event_link, _ids = stack.enter_context(bulk_loader(
            db, tables.EventLink,
            key_columns=['event_id', 'index'], id_column=None))

        for series_slug, series in data['series'].items():
            for event_slug, event in series['events'].items():
                full_start = make_full_datetime(event['start'])
                event_key = (event['city'],
                             full_start.date(), full_start.time())
                event_id = event_ids[event_key]
                for i, talk in enumerate(event.get('talks', ())):
                    insert_talk({
                        'event_id': event_id,
                        'index': i,
                        'title': talk['title'],
                        'description': talk.get('description'),
                        'is_lightning': talk.get('is_lightning', False),
                    })

                for i, url in enumerate(event.get('urls', ())):
                    insert_event_link({
                        'event_id': event_id,
                        'index': i,
                        'url': url,
                    })

    # Load talk speakers and links

    with contextlib.ExitStack() as stack:
        insert_talk_speaker, _ids = stack.enter_context(bulk_loader(
            db, tables.TalkSpeaker,
            key_columns=['talk_id', 'speaker_slug'], id_column=None))
        insert_talk_link, _ids = stack.enter_context(bulk_loader(
            db, tables.TalkLink,
            key_columns=['talk_id', 'url'], id_column=None))

        for series_slug, series in data['series'].items():
            for event_slug, event in series['events'].items():
                for i, talk in enumerate(event.get('talks', ())):
                    full_start = make_full_datetime(event['start'])
                    event_key = (event['city'],
                                 full_start.date(), full_start.time())
                    event_id = event_ids[event_key]
                    talk_id = talk_ids[event_id, i]
                    for i, speaker in enumerate(talk.get('speakers', ())):
                        assert speaker in speaker_slugs
                        insert_talk_speaker({
                            'talk_id': talk_id,
                            'index': i,
                            'speaker_slug': speaker,
                        })

                    for i, link in enumerate([
                            *({'talk': u} for u in talk.get('urls', ())),
                            *talk.get('coverage', {})]):
                        for kind, url in link.items():
                            insert_talk_link({
                                'talk_id': talk_id,
                                'index': i,
                                'url': url,
                                'kind': kind,
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
def bulk_loader(db, orm_class, key_columns=None, id_column='id'):
    if key_columns is None:
        if id_column is None:
            raise ValueError('no key or id column')
        key_columns = [id_column]

    rows = []
    result_map = {}
    table = orm_class.__table__

    yield rows.append, result_map

    if not rows:
        return

    row0_set = set(rows[0])
    if set(key_columns) - row0_set:
        raise ValueError('key columns not in data')

    for row in rows:
        if set(row) != row0_set:
            raise ValueError('uneven table row')

    db.execute(table.insert(), rows)

    if id_column is None:
        return

    if key_columns == [id_column]:
        idmap = {row[id_column]:row[id_column] for row in rows}
    else:
        col_names = [id_column] + key_columns
        columns = [table.c[c] for c in col_names]
        idmap = {tuple(key): i for i, *key in db.execute(select(columns))}

    result_map.update(idmap)
