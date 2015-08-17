import datetime
import collections
import functools

from czech_holidays import Holidays
from dateutil.relativedelta import relativedelta

from pyvodb import tables

DAY = datetime.timedelta(days=1)
WEEK = DAY * 7

MONTH_NAMES = ('? January February March April May June July August September '
    'October November December').split()


def get_calendar(db, first_year=None, first_month=None, num_months=3):
    if first_year is None:
        first_year = datetime.datetime.now().year
    if first_month is None:
        first_month = datetime.datetime.now().month - num_months // 2
    while first_month < 1:
        first_month += 12
        first_year -= 1
    while first_month > 12:
        first_month -= 12
        first_year += 1

    start = datetime.date(year=first_year, month=first_month, day=1)
    end = start + relativedelta(months=num_months)

    query = db.query(tables.Event)
    query = query.filter(tables.Event.date >= start)
    query = query.filter(tables.Event.date < end)
    events = collections.defaultdict(list)
    for event in query:
        events[event.date].append(event)

    months = collections.OrderedDict()
    now = start
    while now < end:
        months[now.year, now.month] = get_month(now.year, now.month, events)
        now += relativedelta(months=1)

    return months

def get_month(year, month, events):
    holidays = {h: h for h in Holidays(year)}
    def mkday(day):
        alien = (day.month != month)
        return get_day(day, events=events, holidays=holidays, alien=alien)

    first_of_month = datetime.date(year, month, 1)
    first = first_of_month - DAY * first_of_month.weekday()

    last = first
    while (last.year, last.month) <= (year, month):
        last += WEEK

    while (last - first) < 6 * WEEK:
        last += WEEK

    week = []
    weeks = []
    current = first
    while current < last:
        if current.weekday() == 0:
            week = []
            weeks.append(week)
        week.append(mkday(current))
        current += DAY

    return weeks


def get_day(day, events, holidays, alien=False):
    return {
        'day': day,
        'events': events[day],
        'holiday': holidays.get(day),
        'weekend': day.weekday() >= 5,
        'alien': alien,
    }
