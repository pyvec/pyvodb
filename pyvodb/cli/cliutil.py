import datetime

import click
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from pyvodb import tables
from pyvodb.dumpers import yaml_dump, json_dump


def handle_raw_output(ctx, data):
    """If a raw output format is set, dump data and exit"""
    if ctx.obj['format'] == 'json':
        print(json_dump(data))
        exit(0)
    if ctx.obj['format'] == 'yaml':
        print(yaml_dump(data), end='')
        exit(0)


def parse_date(date):
    if not date:
        return {'now': True, 'relative': 0}
    elif date.startswith('p'):
        num = -int(date[1:])
        return {'relative': int(num)}
    elif date.startswith('+'):
        num = int(date[1:])
        return {'relative': int(num)}
    elif len(date) == 2:
        return {'date_based': True, 'month': int(date)}
    elif len(date) == 4:
        return {'date_based': True, 'year': int(date)}
    elif len(date) == 5:
        target = datetime.datetime.strptime(date, '%y-%m')
        return {'date_based': True, 'year': target.year, 'month': target.month}
    elif len(date) == 7:
        target = datetime.datetime.strptime(date, '%Y-%m')
        return {'date_based': True, 'year': target.year, 'month': target.month}
    elif len(date) == 8:
        target = datetime.datetime.strptime(date, '%y-%m-%d')
        return {'date_based': True,
                'year': target.year, 'month': target.month, 'day': target.day}
    elif len(date) == 10:
        target = datetime.datetime.strptime(date, '%Y-%m-%d')
        return {'date_based': True,
                'year': target.year, 'month': target.month, 'day': target.day}
    else:
        return {}


def get_city(db, slug):
    try:
        query = db.query(tables.City)
        return query.filter(tables.City.slug.startswith(slug)).one()
    except NoResultFound:
        raise click.UsageError('No such city: %s' % slug)
    except MultipleResultsFound:
        raise click.UsageError('City is not unique: %s' % slug)


def get_event(db, city_slug, date, now):
    city = get_city(db, city_slug)

    query = db.query(tables.Event)
    query = query.filter(tables.Event.city == city)
    dateinfo = parse_date(date)
    if 'now' in dateinfo:
        query = query.filter(tables.Event.date >= now)
        query = query.order_by(tables.Event.date)
        raise_on_many = False
    elif 'relative' in dateinfo:
        rel = dateinfo['relative']
        if rel >= 0:
            query = query.filter(tables.Event.date >= now)
            query = query.order_by(tables.Event.date)
        else:
            query = query.filter(tables.Event.date < now)
            query = query.order_by(tables.Event.date.desc())
        query = query.offset(abs(rel) - 1)
        raise_on_many = False
    elif 'date_based' in dateinfo:
        query = query.filter(tables.Event.year == dateinfo.get('year', now.year))
        if 'month' in dateinfo:
            query = query.filter(tables.Event.month == dateinfo['month'])
        if 'day' in dateinfo:
            query = query.filter(tables.Event.day == dateinfo['day'])
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
