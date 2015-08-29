import collections
import os
import subprocess
import tempfile
import difflib
import traceback
import pathlib
import sys

import click

from pyvodb.load import load_from_infos, slugify
from pyvodb import tables
from pyvodb.dumpers import yaml_dump, yaml_ordered_load

from pyvodb.cli.top import cli
from pyvodb.cli import cliutil


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


def remove_source_file(filename, datadir):
    """Remove the given file, if it's somewhere in the directory datadir"""
    path = pathlib.Path(filename)
    if pathlib.Path(datadir) in path.parents:
        path.unlink()


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
    remove_source_file(previous_source, datadir)
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

    previous_event = cliutil.get_event(db, city, date, today)
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
