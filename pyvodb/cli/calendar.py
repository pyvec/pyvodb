import click

from pyvodb.calendar import get_calendar, MONTH_NAMES, DAY_NAMES

from pyvodb.cli.top import cli
from pyvodb.cli import cliutil


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

    date_info = cliutil.parse_date(date)
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
    cliutil.handle_raw_output(ctx, list(calendar.values()))

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
