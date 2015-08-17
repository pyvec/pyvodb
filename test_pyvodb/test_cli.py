import os
import pytest

from click.testing import CliRunner

from pyvodb.cli import cli

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def run(runner, data_directory, monkeypatch):
    def _run(*args, now='2014-08-07 12:00:00'):
        result = runner.invoke(cli, ('--data', data_directory) + args,
                               env={'PYVO_TEST_NOW': now},
                               obj={})
        if result.exc_info and not isinstance(result.exc_info[1], SystemExit):
            raise result.exc_info[1]
        print(result.output)
        return result

    return _run


def test_help(run):
    result = run('--help')
    assert result.exit_code == 0
    assert result.output.startswith('Usage: cli [OPTIONS] COMMAND [ARGS]...')


def test_show_help(run):
    result = run('show', '--help')
    assert result.exit_code == 0
    assert result.output.startswith('Usage: cli show [OPTIONS] CITY [DATE]')


def test_alias_help(run):
    result = run('sho', '--help')
    assert result.exit_code == 0
    assert result.output.startswith('Usage: cli show [OPTIONS] CITY [DATE]')


def test_show_now(run, get_yaml_data):
    result = run('show', 'ostrava')
    assert result.exit_code == 0
    assert result.output == get_yaml_data('ostrava/2014-08-07*.yaml')


def test_show_no_upcoming(run, get_yaml_data):
    result = run('show', 'brno', now='2099-01-01 00:00:00')
    assert result.exit_code == 'No such meetup'  # SystemExit('No such meetup')


@pytest.mark.parametrize(['filename', 'args'], [
    ['brno/2015-02-26*.yaml', ('brno', )],
    ['ostrava/2013-12-04*.yaml', ('ostrava', 'p1')],
    ['ostrava/2013-11-07*.yaml', ('ostrava', 'p2')],
    ['ostrava/2014-08-07*.yaml', ('ostrava', '+1')],
    ['ostrava/2014-10-02*.yaml', ('ostrava', '+2')],
    ['ostrava/2014-11-06*.yaml', ('ostrava', '11')],
    ['ostrava/2013-11-07*.yaml', ('ostrava', '13-11')],
    ['ostrava/2013-11-07*.yaml', ('ostrava', '2013-11')],
    ['ostrava/2013-11-07*.yaml', ('ostrava', '13-11-07')],
    ['ostrava/2013-11-07*.yaml', ('ostrava', '2013-11-07')],
])
def test_show_event(run, get_yaml_data, args, filename):
    result = run('show',  *args)
    assert result.exit_code == 0
    assert result.output == get_yaml_data(filename)


@pytest.mark.parametrize(['message', 'args'], [
    ['No such meetup', ('brno', 'p100')],
    ['No such meetup', ('brno', '+1000')],
    ['No such meetup', ('brno', '1876-10')],
])
def test_show_event_negative(run, get_yaml_data, args, message):
    result = run('show',  *args)
    assert result.exit_code == message
