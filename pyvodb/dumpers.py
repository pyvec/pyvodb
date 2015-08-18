import json
import collections
import datetime

import yaml
from czech_holidays import Holiday

from pyvodb import tables

def yaml_dump(data):
    return yaml.dump(data, Dumper=EventDumper)

def json_dump(data):
    return JsonEncoder(ensure_ascii=False, indent=2).encode(data)


class EventDumper(yaml.SafeDumper):
    def __init__(self, *args, **kwargs):
        kwargs['default_flow_style'] = False
        kwargs['allow_unicode'] = True
        super(EventDumper, self).__init__(*args, **kwargs)


def _dict_representer(dumper, data):
    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        data.items())


def _event_representer(dumper, data):
    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        data.as_dict())


def _holiday_representer(dumper, data):
    return dumper.represent_scalar(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data.name)

EventDumper.add_representer(collections.OrderedDict, _dict_representer)
EventDumper.add_representer(tables.Event, _event_representer)
EventDumper.add_representer(Holiday, _holiday_representer)


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.date):
            return str(obj)
        elif isinstance(obj, tables.Event):
            return obj.as_dict()
        return super().default(obj)


class OrderedLoader(yaml.SafeLoader):
    pass

def construct_mapping(loader, node):
    loader.flatten_mapping(node)
    return collections.OrderedDict(loader.construct_pairs(node))

OrderedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping)

def yaml_ordered_load(data):
    return yaml.load(data, OrderedLoader)
