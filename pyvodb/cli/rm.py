
import click

from pyvodb.cli.top import cli
from pyvodb.cli.edit import remove_source_file
from pyvodb.cli import cliutil


@cli.command()
@click.argument('city')
@click.argument('date', required=False)
@click.pass_context
def rm(ctx, city, date):
    """Remove a particular meetup.

    city: The meetup series.
    date: The date. See `pyvo show --help` for format.
    """
    db = ctx.obj['db']
    today = ctx.obj['now'].date()
    datadir = ctx.obj['datadir']

    event = cliutil.get_event(db, city, date, today)
    db.delete(event)
    if event._source:
        remove_source_file(event._source, datadir)

    db.commit()
