import logging
import datetime
import collections
import os

import click
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
import yaml

from pyvodb.load import get_db
from pyvodb import tables


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


def main():
    return cli(obj={})


class EventDumper(yaml.SafeDumper):
    def __init__(self, *args, **kwargs):
        kwargs['default_flow_style'] = False
        kwargs['allow_unicode'] = True
        super(EventDumper, self).__init__(*args, **kwargs)

def _dict_representer(dumper, data):
    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        data.items())

EventDumper.add_representer(collections.OrderedDict, _dict_representer)


def list_cities(header, db):
    print(header)
    for city in db.query(tables.City):
        print('  ' + city.slug)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option('--data', help="Data directory", default='.', envvar='PYVO_DATA')
@click.option('-v/-q', '--verbose/--quiet')
@click.pass_context
def cli(ctx, data, verbose):
    """Manipulate and query a meetup database
    """
    if verbose:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    ctx.obj['db'] = get_db(data)
    if 'PYVO_TEST_NOW' in os.environ:
        # Fake the current date for testing
        ctx.obj['now'] = datetime.datetime.strptime(
            os.environ['PYVO_TEST_NOW'], '%Y-%m-%d %H:%M:%S')
    else:
        ctx.obj['now'] = datetime.datetime.now()


def get_event(db, city_obj, date, now):
    query = db.query(tables.Event)
    query = query.filter(tables.Event.city == city_obj)
    if not date:
        query = query.filter(tables.Event.date >= now)
        query = query.order_by(tables.Event.date)
        raise_on_many = False
    elif date.startswith('p'):
        query = query.filter(tables.Event.date < now)
        query = query.order_by(tables.Event.date.desc())
        query = query.offset(int(date[1:]) - 1)
        raise_on_many = False
    elif date.startswith('+'):
        query = query.filter(tables.Event.date >= now)
        query = query.order_by(tables.Event.date)
        query = query.offset(int(date[1:]) - 1)
        raise_on_many = False
    elif len(date) == 2:
        query = query.filter(tables.Event.year == now.year)
        query = query.filter(tables.Event.month == int(date))
        raise_on_many = True
    elif len(date) == 5:
        target = datetime.datetime.strptime(date, '%y-%m')
        query = query.filter(tables.Event.year == target.year)
        query = query.filter(tables.Event.month == target.month)
        raise_on_many = True
    elif len(date) == 7:
        target = datetime.datetime.strptime(date, '%Y-%m')
        query = query.filter(tables.Event.year == target.year)
        query = query.filter(tables.Event.month == target.month)
        raise_on_many = True
    elif len(date) == 8:
        target = datetime.datetime.strptime(date, '%y-%m-%d')
        query = query.filter(tables.Event.year == target.year)
        query = query.filter(tables.Event.month == target.month)
        query = query.filter(tables.Event.day == target.day)
        raise_on_many = True
    elif len(date) == 10:
        target = datetime.datetime.strptime(date, '%Y-%m-%d')
        query = query.filter(tables.Event.year == target.year)
        query = query.filter(tables.Event.month == target.month)
        query = query.filter(tables.Event.day == target.day)
        raise_on_many = True
    else:
        raise click.UsageError('Unknown date format')

    if raise_on_many:
        try:
            event = query.one()
        except NoResultFound:
            raise SystemExit('No such meetup')
        except MultipleResultsFound:
            raise SystemExit('Multiple meetups match')
    else:
        event = query.first()
        if event is None:
            raise SystemExit('No such meetup')

    return event


@cli.command()
@click.argument('city')
@click.argument('date', required=False)
@click.pass_context
def show(ctx, city, date):
    """Show a particular meetup

    city: The meetup series.

    \b
    date: The date. May be:
        - YYYY-MM-DD or YY-MM-DD (e.g. 2015-08-27)
        - YYYY-MM or YY-MM (e.g. 2015-08)
        - MM (e.g. 08): the given month in the current year
        - pN (e.g. p1): show the N-th last meetup
        - +N (e.g. +2): show the N-th next meetup
        - Omitted: show the next meetup (same as +1)
    """
    db = ctx.obj['db']
    try:
        city_obj = db.query(tables.City).filter(tables.City.slug.startswith(city)).one()
    except NoResultFound:
        raise click.UsageError('No such city: %s' % city)
    except MultipleResultsFound:
        raise click.UsageError('City is not unique: %s' % city)

    event = get_event(db, city_obj, date, ctx.obj['now'].date())

    print(yaml.dump(event.as_dict(), Dumper=EventDumper), end='')
