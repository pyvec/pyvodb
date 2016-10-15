import logging
import datetime
import os
import shlex

import click
import blessings

from pyvodb.load import get_db


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
    """Query a meetup database.
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
