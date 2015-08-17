import os
import datetime

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql.expression import select, and_, or_

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


def yield_filenames(directory):
    """Yield YAML data filenames from a root directory
    """
    directories = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if (d in ('.', '..') or
                                               not d.startswith('.'))]
        directories.extend(os.path.join(directory, dirpath, d)
                           for d in dirnames)
    for directory in directories:
        for filename in os.listdir(directory):
            if filename.endswith('.yaml'):
                yield os.path.join(directory, filename)


def load_from_directory(db, directory):
    """Add data from a directory to a database
    """
    infos = (get_info(f) for f in yield_filenames(directory))
    load_from_infos(db, infos)


def load_from_file(db, filename):
    """Add data from a single file to a database
    """
    info = get_info(filename)
    load_from_infos(db, [info])


def get_info(filename):
    with open(filename) as f:
        info = yaml.load(f, Loader=YAML_SAFE_LOADER)
    return info


def one(container):
    [obj] = container
    return obj


def _fixup(infos):
    for info in infos:
        info = dict(info)
        start = info['start']
        if hasattr(start, 'time'):
            date = start.date()
            time = start.time()
        else:
            date = start
            time = datetime.time(hour=19)
        info['start'] = datetime.datetime.combine(date, time)
        yield info


def load_from_infos(db, infos):
    """Load data from a list of info dicts (as loaded from YAML) into database
    """
    # The ORM overhead is too high for this kind of bulk load,
    # so drop down to SQLAlchemy Core.
    # This tries to do minimize the number of SQL commands by loading entire
    # tables at once
    infos = tuple(_fixup(infos))
    try:
        # First, entries that might already exist.
        # If they do, don't create duplicates, but check that they new
        # and existing entries are the same.
        # In other words, we don't do updates here.
        city_ids = load_cities(db, infos)
        venue_ids = load_venues(db, infos)
        speaker_ids = load_speakers(db, infos)

        # For events, we don't allow re-adding an existing entry
        event_ids = load_events(db, infos, city_ids, venue_ids)

        # All talks must be tied to a newly added event
        talk_ids = load_talks(db, infos, event_ids, city_ids)

        # Last but not least come the ID-less tables, all of which are also
        # tied to a newly added event.
        talk_speaker_values = [
            {
                'speaker_id': speaker_ids[s, ],
                'talk_id': talk_ids[e['_id'], ti],
                'index': si,
            }
            for e in infos
            for ti, t in enumerate(e['talks'])
            for si, s in enumerate(t.get('speakers', ()))
        ]
        if talk_speaker_values:
            db.execute(tables.TalkSpeaker.__table__.insert(), talk_speaker_values)

        talk_link_values = [
            {
                'talk_id': talk_ids[e['_id'], ti],
                'index': li,
                'kind': one(l.keys()),
                'url': one(l.values()),
            }
            for e in infos
            for ti, t in enumerate(e['talks'])
            for li, l in enumerate([{'talk': u} for u in t.get('urls', ())] +
                                   t.get('coverage', []))
        ]
        if talk_link_values:
            db.execute(tables.TalkLink.__table__.insert(), talk_link_values)

        event_link_values = [
            {
                'event_id': e['_id'],
                'index': li,
                'url': l,
            }
            for e in infos
            for li, l in enumerate(e.get('urls', ()))
        ]
        if event_link_values:
            db.execute(tables.EventLink.__table__.insert(), event_link_values)

    except:
        db.rollback()
        raise
    else:
        db.commit()


def load_cities(db, infos):

    def make_values(info):
        name = info['city']
        return {
            'name': name,
            'slug': tables.slugify(name),
        }

    return bulk_load(
        db=db,
        sources=[make_values(i) for i in infos],
        table=tables.City.__table__,
        key_columns=('name', ),
    )


def load_venues(db, infos):

    def make_values(info):
        return {
            'name': info['name'],
            'city': info['city'],
            'address': info.get('address'),
            'longitude': info['location']['longitude'],
            'latitude': info['location']['latitude'],
            'slug': tables.slugify(info['name']),
        }

    return bulk_load(
        db=db,
        sources=[make_values(i['venue']) for i in infos],
        table=tables.Venue.__table__,
        key_columns=('name', ),
        ignored_columns=('address', ),  # XXX: addresses from Lanyrd are unreliable
    )


def load_events(db, infos, city_ids, venue_ids):

    def make_values(info):
        result = {
            'name': info['name'],
            'number': info.get('number'),
            'topic': info.get('topic'),
            'description': info.get('description'),
            'date': info['start'].date(),
            'start_time': info['start'].time(),
            'city_id': city_ids[(info['city'], )],
            'venue_id': venue_ids[(info['venue']['name'], )],
        }
        return result

    sources = [make_values(i) for i in infos]
    idmap = bulk_load(
        db=db,
        sources=sources,
        table=tables.Event.__table__,
        key_columns=('city_id', 'date', 'start_time'),
        no_existing=True,
    )
    for source, info in zip(sources, infos):
        info['_id'] = idmap[source['city_id'], source['date'], source['start_time']]
    return idmap


def load_speakers(db, infos):

    return bulk_load(
        db=db,
        sources=[{'name': s}
                 for i in infos
                 for t in i['talks']
                 for s in t.get('speakers', ())],
        table=tables.Speaker.__table__,
        key_columns=('name', ),
    )


def load_talks(db, infos, event_ids, city_ids):

    def make_values(index, event_info, talk_info):
        city_id = city_ids[(event_info['city'], )]
        event_key = city_id, event_info['start'].date(), event_info['start'].time()
        return {
            'title': talk_info['title'],
            'index': index,
            'is_lightning': talk_info.get('lightning', False),
            'event_id': event_info['_id'],
            'description': talk_info.get('description'),
        }

    return bulk_load(
        db=db,
        sources=[make_values(i, e, t)
                 for e in infos
                 for i, t in enumerate(e['talks'])],
        table=tables.Talk.__table__,
        key_columns=('event_id', 'index'),
    )


def _get_idmap(rows, key_col_count, keys):
    kv = ((tuple(row[:key_col_count]), row[key_col_count]) for row in rows)
    return {k: v for k, v in kv if k in keys}


def _yaml_dump(obj):
    return yaml.safe_dump(obj, default_flow_style=False, allow_unicode=True)


def _check_entry(expected, got, ignored_keys=()):
    for key in (expected.keys() | got.keys()).difference(ignored_keys):
        if expected[key] != got[key]:
            print(_yaml_dump(expected))
            print(_yaml_dump(got))
            raise ValueError('Attempting to overwrite existing entry')


def bulk_load(db, sources, table, key_columns, id_column='id',
              no_existing=False, ignored_columns=()):
    """Load data into the database

    :param db: The SQLAlchemy session
    :param sources: A list of dictionaries containing the values to insert
    :param table: The SQLAlchemy table to operate on
    :param key_columns: Names of unique-key columns
    :param id_column: Name of the surrogate primary key column
    :param no_existing: If true, disallow duplicates of entries already in the DB
    :param ignored_columns: Columns ignored in duplicate checking

    Returns an ID map: a dictionary of keys (values from columns given by
    key_columns) to IDs.
    """

    # Get a dict of key -> source, while checking that sources with duplicate
    # keys also have duplicate data

    source_dict = {}
    for source in sources:
        key = tuple(source[k] for k in key_columns)
        if key in source_dict:
            _check_entry(source_dict[key], source, ignored_columns)
        else:
            source_dict[key] = source
    if not source_dict:
        return
    keys = set(source_dict)

    # List of column objects (key + id)
    col_list = [table.c[k] for k in key_columns] + [table.c[id_column]]

    def get_whereclause(keys):
        """WHERE clause that selects all given keys
        (may give some extra ones)
        """
        if len(key_columns) == 1:
            return table.c[key_columns[0]].in_(k for [k] in keys)
        else:
            return and_(table.c[c].in_(set(k[i] for k in keys))
                        for i, c in enumerate(key_columns))

    # Non-key & non-id column names
    check_columns = [c for c in sources[0] if c not in key_columns]

    # Get existing entries, construct initial ID map
    sel = select(col_list + [table.c[k] for k in check_columns],
                 whereclause=get_whereclause(keys))
    existing_rows = list(db.execute(sel))
    id_map = _get_idmap(existing_rows, len(key_columns), keys)

    # Check existing entries are OK
    if no_existing and id_map:
        raise ValueError('Attempting to overwrite existing entry')
    if check_columns:
        for row in existing_rows:
            key = tuple(row[:len(key_columns)])
            source = source_dict[key]
            for n, v in zip(check_columns, row[len(key_columns)+1:]):
                if n not in ignored_columns:
                    if source[n] != v:
                        raise ValueError('Attempting to overwrite existing entry')

    # Insert the missing rows into the DB; then select them back to read the IDs
    values = []
    missing = set()
    for key, source in source_dict.items():
        if key not in id_map and key not in missing:
            values.append(source)
            missing.add(key)
    if values:
        db.execute(table.insert(), values)
        sel = select(col_list, whereclause=get_whereclause(missing))
        id_map.update(_get_idmap(db.execute(sel), len(key_columns), keys))

    return id_map
