import textwrap

import click

from pyvodb.cli.top import cli
from pyvodb.cli import cliutil
from pyvodb.calendar import MONTH_NAMES, DAY_NAMES


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

    event = cliutil.get_event(db, city, date, today)

    data = event.as_dict()
    cliutil.handle_raw_output(ctx, data)
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
        print(', {}'.format(event.venue.city.name), end='')
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
