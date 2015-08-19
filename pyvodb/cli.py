import logging
import datetime
import collections
import os
import textwrap
import subprocess
import tempfile
import shlex
import difflib
import traceback
import pathlib
import sys

import click
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
import blessings
import yaml

from pyvodb.load import get_db, load_from_infos, slugify
from pyvodb import tables
from pyvodb.calendar import get_calendar, MONTH_NAMES, DAY_NAMES
from pyvodb.dumpers import yaml_dump, json_dump, yaml_ordered_load


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
@click.option('--editor', envvar=['PYVO_EDITOR', 'VISUAL', 'EDITOR'],
              help="Your preferred editor (preferably console-based)")
@click.option('-v/-q', '--verbose/--quiet', help="Spew lots of information")
@click.pass_context
def cli(ctx, data, verbose, color, format, editor):
    """Manipulate and query a meetup database.
    """
    ctx.obj['verbose'] = verbose
    if verbose:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    ctx.obj['datadir'] = os.path.abspath(data)
    if 'db' not in ctx.obj:
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
    ctx.obj['editor'] = shlex.split(editor)


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
    today = ctx.obj['now'].date()
    term = ctx.obj['term']

    event = get_event(db, city, date, today)

    data = event.as_dict()
    handle_raw_output(ctx, data)
    render_event(term, event, today, verbose=ctx.obj['verbose'])

def render_event(term, event, today, verbose=False):
    term_width = min(term.width or 70, 70)
    day_diff = (event.date - today).days
    if day_diff == 0:
        msg = "we're meeting"
    elif day_diff < 0:
        msg = "we met"
    else:
        msg = "we'll meet"
    print('{d} ({day}, {month} {d.day}, {d.year}) {msg} at the {city} meetup'.format(
        d=event.date, day=DAY_NAMES[event.date.weekday()],
        month=MONTH_NAMES[event.date.month], msg=msg, city=event.city.name))
    print()
    print(' ', render_event_title(term, event))
    print()
    if event.description:
        for line in textwrap.wrap(event.description, term_width):
            print('    {}'.format(line.expandtabs(4)))
        print()
    print('at {}'.format(term.bold(event.venue.name)), end='')
    if event.venue.address:
        print(', {}'.format(event.venue.address), end='')
    if event.venue.address:
        print(', {}'.format(event.venue.city), end='')
    print()
    print('  {v.latitude} N, {v.longitude} E'.format(v=event.venue))
    print('  http://mapy.cz/zakladni?x={v.longitude}&y={v.latitude}&z=17'.format(v=event.venue))
    print()
    if event.talks:
        print('Talks:')
        for talk in event.talks:
            if talk.is_lightning:
                print(term.bold_yellow(' \N{HIGH VOLTAGE SIGN} '), end='')
            else:
                print('  ', end='')
            if talk.speakers:
                print('{}: '.format(', '.join(s.name for s in talk.speakers)), end='')
            print(term.bold(talk.title))
            if talk.description:
                for line in textwrap.wrap(talk.description, term_width):
                    print('      {}'.format(line))
            for link in talk.links:
                if link.youtube_id:
                    sigil = '[>] '
                else:
                    sigil = ''
                print('    {}{}'.format(sigil, link.url))
            print()

    if event.links:
        print('More info online:')
        for link in event.links:
            print('  {}'.format(link.url))

    if verbose and event._source:
        print()
        print('entry loaded from {}'.format(event._source))


def render_event_title(term, event):
    parts = [(2, event.name)]
    if event.number is not None:
        parts.append((1, '#{}'.format(event.number)))
    elif event.topic:
        parts.append((0, '–'))
    if event.topic:
        parts.append((3, event.topic))
    max_weight = max(w for w, t in parts)
    return ' '.join(term.bold(t) if w == max_weight else t
                    for w, t in parts)


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


def event_filename(info):
    try:
        get = info.get
    except AttributeError:
        return '<not a dict>'
    parts = []
    if get('start'):
        parts.append(str(get('start').date()))
    if get('topic'):
        if parts:
            parts.append('-')
        parts.append(slugify(get('topic')))
    if get('city'):
        parts.insert(0, slugify(get('city')) + '/')
    parts.append('.yaml')
    return ''.join(parts)


def show_diff(term, a, b, a_filename, b_filename):
    if a == b:
        print(term.yellow('No changes!'))
        print(a)
        return
    for line in difflib.unified_diff(
            a.splitlines(keepends=True),
            b.splitlines(keepends=True),
            a_filename, b_filename, n=max(len(a), len(b))):
        if line.startswith('+'):
            print(term.green(line), end='')
        elif line.startswith('-'):
            print(term.red(line), end='')
        elif line.startswith('@'):
            print(term.yellow(line), end='')
        else:
            print(line, end='')


def ask(term, prompt, options, *, default=None):
    assert(c == c.lower() for c in options)

    if len(options) == 1:
        [answer] = options
        return answer

    menu_options = collections.OrderedDict(options)
    menu_options.setdefault('?', 'print this help')
    menu = '[{}]'.format('/'.join(o.upper() if o == default else o
                                  for o in menu_options))
    full_prompt = '{} {} '.format(term.blue(prompt), menu)

    while True:
        answer = input(full_prompt).lower()
        if answer in options:
            return answer
        if not answer and default:
            return default
        if answer not in ('?', 'help'):
            print(term.yellow('Please select one of the options:'))
        for letter, help in menu_options.items():
            print('{}: {}'.format(term.yellow(letter), help))


def load_new_entry(db, term, datadir, previous_entry, info):
    """Load a new entry from `info`, pausing for confirmation

    Returns an iterator for a two-part loading process:
    - after a first next(), the session is left with an open transaction
      that has all the data. All load errors should be raised from this first
      phase
    - after a second next(), the DB is comitted, and data files are written out

    :param db: Database session
    :param term: blessings.Terminal for output. None for silent operation
    :param datadir: Root directory for data (files outside this aren't modified)
    :param previous_entry: The previous Event, which will be deleted
    :param info: Dict with new event info
    """
    previous_source = previous_entry._source
    try:
        phase = 'doing sanity check'
        city = info['city']

        phase = 'rolling back transaction'
        db.rollback()

        phase = 'deleting previous entry'
        db.delete(previous_entry)
        db.flush()

        phase = 'adding new entry'
        info['_source'] = os.path.join(
            datadir, event_filename(info))
        [event_id] = load_from_infos(db, [info], commit=False)
        del info['_source']

    except Exception:
        if term:
            print(term.red('Error {}'.format(phase)))
        raise

    new_entry = db.query(tables.Event).get(event_id)
    yaml_data = yaml_dump(new_entry.as_dict())
    yield yaml_data

    db.commit()
    prev_src_path = pathlib.Path(previous_source)
    if pathlib.Path(datadir) in prev_src_path.parents:
        prev_src_path.unlink()
    new_path = os.path.join(datadir, event_filename(info))
    try:
        os.makedirs(os.path.dirname(new_path))
    except FileExistsError:
        pass
    with open(new_path, 'w') as f:
        f.write(yaml_data)


@cli.command()
@click.argument('city')
@click.argument('date', required=False)
@click.option('-i/-I', '--interactive/--no-interactive', default=None,
              help='Ask for opions interactively, and edit in editor '
                   '(default if stdin is a TTY).\n'
                   'For non-interactive use, new entry is expected on stdin')
@click.pass_context
def edit(ctx, city, date, interactive):
    """Edit a particular meetup.

    city: The meetup series.
    date: The date. See `pyvo show --help` for format.
    """
    db = ctx.obj['db']
    today = ctx.obj['now'].date()
    term = ctx.obj['term']
    editor = ctx.obj['editor']
    datadir = ctx.obj['datadir']

    if interactive is None:
        interactive = sys.stdin.isatty()

    previous_event = get_event(db, city, date, today)
    previous_source = previous_event._source

    if not interactive:
        yaml_data = sys.stdin.read()
        assert yaml_data
        info = yaml_ordered_load(yaml_data)
        load_process = load_new_entry(db, term, datadir, previous_event, info)
        next(load_process)
        # No confirmation step in non-interactive mode
        next(load_process, None)
        return

    previous_dict = info = previous_event.as_dict()
    previous_data = yaml_dump(previous_dict)

    def show_current_diff():
        if previous_source:
            psrc = os.path.join(datadir, previous_source)
            psrc = os.path.relpath(psrc, datadir)
        show_diff(term, previous_data, yaml_data,
                  psrc or event_filename(previous_dict),
                  event_filename(info))

    fd, temp_filename = tempfile.mkstemp(suffix='.yaml')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(previous_data)
        subprocess.check_call(editor + [temp_filename])

        while True:
            with open(temp_filename) as f:
                yaml_data = f.read()

            prompt = 'Action?'
            options = collections.OrderedDict()
            default = None

            try:
                info = yaml_ordered_load(yaml_data)

                load_process = load_new_entry(db, term, datadir,
                                              previous_event, info)
                yaml_data = next(load_process)

                show_current_diff()
            except Exception as e:
                print('{}: {}'.format(type(e).__name__, e))
                prompt = 'Re-edit or quit?'
                options['e'] = 're-edit'
                options['t'] = 'show error traceback'
                saved_error = e
                default = 'e'
            else:
                prompt = 'Save this change?'
                options['y'] = 'save entry'
                default = 'y'

            options['e'] = 're-edit'
            # XXX: a debug option to enable this?
            #options['i'] = 'debug with interactive Python console'
            options['d'] = 'show current diff'
            options['q'] = 'quit'

            while True:
                # inner loop for asking; options that don't change contents
                # of the date (i.e. temp file) should loop here
                # after a "break" we'll re-read data & show updated diff

                answer = ask(term, prompt, options, default=default)

                if answer == 'e':
                    subprocess.check_call(editor + [temp_filename])
                    break
                elif answer == 'y':
                    next(load_process, None)
                    return
                elif answer == 'q':
                    print(term.yellow('The file you are abandoning:'))
                    print(yaml_data)
                    return
                elif answer == 'i':
                    import code
                    code.interact(local=locals())
                    continue
                elif answer == 'd':
                    show_current_diff()
                    continue
                elif answer == 't':
                    traceback.print_exception(type(saved_error), saved_error,
                                              saved_error.__traceback__)
                else:
                    continue

    finally:
        db.rollback()
        os.unlink(temp_filename)
