import logging
import datetime
import collections
import os

import click
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
import blessings

from pyvodb.load import get_db
from pyvodb import tables
from pyvodb.calendar import get_calendar, MONTH_NAMES
from pyvodb.dumpers import yaml_dump, json_dump


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


def main():
    return cli(obj={})


class AliasedGroup(click.Group):
    """Allow short aliases of commands"""
    # http://click.pocoo.org/5/advanced/#command-aliases
    def get_command(self, ctx, cmd_name):
        rv = super().get_command(ctx, cmd_name)
        if rv is not None:
            return rv
        matches = [x for x in self.list_commands(ctx)
                   if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            cmd = super().get_command(ctx, matches[0])
            ctx.invoked_subcommand = matches[0]
            return cmd
        ctx.fail('Ambiguous command: could be %s' % ', '.join(sorted(matches)))

    def command(self, *args, **kwargs):
        kwargs.setdefault('cls', Command)
        return super().command(*args, **kwargs)


class Command(click.Command):
    """Keep original names of commands, even if aliased"""
    def make_context(self, cmd_name, *args, **kwargs):
        return super().make_context(self.name, *args, **kwargs)


@click.group(context_settings=CONTEXT_SETTINGS, cls=AliasedGroup)
@click.option('--data', help="Data directory", default='.', envvar='PYVO_DATA')
@click.option('--color/--no-color', default=None,
              help="Enable or disable color output (Default is to only use color for terminals)")
@click.option('--yaml', 'format', flag_value='yaml', help="Export raw data as JSON")
@click.option('--json', 'format', flag_value='json', help="Export raw data as YAML")
@click.option('-v/-q', '--verbose/--quiet')
@click.pass_context
def cli(ctx, data, verbose, color, format):
    """Manipulate and query a meetup database.
    """
    if verbose:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    ctx.obj['datadir'] = data
    ctx.obj['db'] = get_db(data)
    if color is None:
        ctx.obj['term'] = blessings.Terminal()
    elif color is True:
        ctx.obj['term'] = blessings.Terminal(force_styling=True)
    elif color is False:
        ctx.obj['term'] = blessings.Terminal(force_styling=None)
    if 'PYVO_TEST_NOW' in os.environ:
        # Fake the current date for testing
        ctx.obj['now'] = datetime.datetime.strptime(
            os.environ['PYVO_TEST_NOW'], '%Y-%m-%d %H:%M:%S')
    else:
        ctx.obj['now'] = datetime.datetime.now()
    ctx.obj['format'] = format


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
        return {'relative': -int(date[1:])}
    elif date.startswith('+'):
        num = -int(date[1:])
        return {'relative': int(date[1:])}
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


def get_event(db, city_obj, date, now):
    query = db.query(tables.Event)
    query = query.filter(tables.Event.city == city_obj)
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


@cli.command()
@click.argument('city')
@click.argument('date', required=False)
@click.pass_context
def show(ctx, city, date):
    """Show a particular meetup.

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

    data = event.as_dict()
    handle_raw_output(ctx, data)

    print(yaml_dump(data), end='')


@cli.command()
@click.option('--agenda/--no-agenda', default=None,
              help='Show a list of events appearing in the calendar.')
@click.option('-y', '--year', help='Show the whole year', is_flag=True)
@click.argument('date', required=False)
@click.pass_context
def calendar(ctx, date, agenda, year):
    """Show a 3-month calendar of meetups.

    \b
    date: The date around which the calendar is centered. May be:
        - YYYY-MM-DD, YY-MM-DD, YYYY-MM or YY-MM (e.g. 2015-08)
        - MM (e.g. 08): the given month in the current year
        - pN (e.g. p1): N-th last month
        - +N (e.g. +2): N-th next month
        - Omitted: today
        - YYYY: Show the entire year, as with -y
    """
    do_full_year = year
    today = ctx.obj['now'].date()
    db = ctx.obj['db']
    term = ctx.obj['term']

    date_info = parse_date(date)
    if 'relative' in date_info:
        year = today.year
        month = today.month + date_info['relative']
    elif 'date_based' in date_info:
        year = date_info.get('year', today.year)
        month = date_info.get('month', today.month)
        if 'month' not in date_info and 'day' not in date_info:
            do_full_year = True
    else:
        raise click.UsageError('Unknown date format')

    if agenda is None:
        agenda = not do_full_year

    if do_full_year:
        first_month = 1
        num_months = 12
    else:
        first_month = month - 1
        num_months = 3

    calendar = get_calendar(db, year, first_month, num_months)
    handle_raw_output(ctx, list(calendar.values()))

    render_calendar(term, calendar, today, agenda)

def render_calendar(term, calendar, today=None, agenda=False):
    calendar_items = list(calendar.items())

    while calendar_items:
        calendar_keys = [k for k, v in calendar_items[:3]]
        calendar_values = [v for k, v in calendar_items[:3]]

        for year, month in calendar_keys:
            print(MONTH_NAMES[month].center(7*3+1), end='')
        print()
        for year, month in calendar_keys:
            print('{0:04}-{1:02}'.format(year, month).center(7*3+1), end='')
        print()

        print(term.blue(' Mo Tu We Th Fr Sa Su ' * len(calendar_keys)))
        next_sepchar = ' '
        for weeks in zip(*calendar_values[:3]):
            for week in weeks:
                for day in week:
                    sepchar = next_sepchar
                    next_sepchar = ' '
                    color = str
                    if day['alien']:
                        representation = '  '
                    else:
                        if day['day'] == today:
                            color = term.bold
                            if day['holiday'] or day['weekend']:
                                color = term.bold_blue
                        elif day['holiday'] or day['weekend']:
                            color = term.blue
                        if day['events']:
                            count = len(day['events'])
                            if count > 1:
                                representation = '**'
                            else:
                                representation = day['events'][0].city.slug[:2]
                            color = term.bold_red
                        else:
                            representation = str(day['day'].day)
                        if day['day'] == today:
                            sepchar = term.bold('[')
                            next_sepchar = term.bold(']')
                    print(sepchar + color(representation.rjust(2)), end='')
                print(end=next_sepchar)
                next_sepchar = ' '
            print()
        calendar_items = calendar_items[3:]

    if agenda:
        for (year, month), weeks in calendar.items():
            need_nl = True
            for week in weeks:
                for day in week:
                    if not day['alien']:
                        for event in day['events']:
                            if need_nl:
                                print()
                                print('{}:'.format(MONTH_NAMES[month]))
                                need_nl = False
                            date = event.date
                            city = event.city.slug
                            if len(day['events']) > 2:
                                date = term.bold_red(str(date))
                            else:
                                city = term.bold_red(city[:2]) + city[2:].ljust(7)
                            print('{} {} {}'.format(city, date, event.title))
