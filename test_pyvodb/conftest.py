import os
import glob

import pytest

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
