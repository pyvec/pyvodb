import os

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import tables

def load_event(session, info):
    event = tables.Event.from_dict(info, db=session)
    session.add(event)

def load_dir(session, directory):
    for filename in os.listdir(directory):
        if filename.endswith('.yaml'):
            with open(os.path.join(directory, filename)) as f:
                load_event(session, yaml.safe_load(f))
    session.commit()
    session.flush()

def get_db(directory, engine=None):
    directories = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if (d in ('.', '..') or
                                               not d.startswith('.'))]
        directories.extend(os.path.join(directory, dirpath, d)
                           for d in dirnames)
    if engine is None:
        engine = create_engine('sqlite://')
    tables.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    for directory in directories:
        load_dir(session, directory)
    return session
