import os

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import tables

def load_event(session, info):
    event = tables.Event(
        name=info['name'],
        number=info.get('number'),
        topic=info.get('topic'),
        desription=info.get('desription'),
    )
    session.add(event)

def load_dir(session, directory):
    for filename in os.listdir(directory):
        if filename.endswith('.yaml'):
            with open(os.path.join(directory, filename)) as f:
                load_event(session, yaml.safe_load(f))
    session.commit()
    session.flush()

def get_db(directories=None):
    if directories is None:
        directories = []
        base_path = os.path.join(os.path.dirname(__file__), 'data')
        for dirpath, dirnames, filenames in os.walk(base_path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            directories.extend(os.path.join(base_path, dirpath, d)
                               for d in dirnames)
    engine = create_engine('sqlite://')
    tables.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    for directory in directories:
        load_dir(session, directory)
    return session
