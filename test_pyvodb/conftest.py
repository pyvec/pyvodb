import os
import glob

import pytest

from pyvodb.load import get_db

@pytest.fixture(scope='module')
def data_directory():
    return os.path.join(os.path.dirname(__file__), 'data')

@pytest.fixture
def get_yaml_data(data_directory):
    def _get_yaml_data(filename):
        [filename] = glob.glob(os.path.join(data_directory, filename))
        with open(filename) as f:
            return f.read()
    return _get_yaml_data

@pytest.fixture(scope='module')
def db(data_directory):
    return get_db(data_directory)
