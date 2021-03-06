import os
import pytest
import textwrap
import sys
import builtins
import re

from click.testing import CliRunner
import yaml
from sqlalchemy.orm.exc import NoResultFound

from pyvodb.cli import cli
from pyvodb.load import get_db
from pyvodb import tables
from pyvodb import cli as pyvodb_cli_module

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def run(runner, data_directory, monkeypatch):
    def _run(*args, now='2014-08-07 12:00:00', datadir=data_directory,
             stdin_text=None, db=None):
        if stdin_text and os.environ.get('TRAVIS') == 'true':
            raise pytest.skip("stdin redirection doesn't work on Travis")
        prev_stdin = sys.stdin
        try:
            obj = {}
            if db:
                obj['db'] = db
            result = runner.invoke(cli, ('--data', datadir) + args,
                                   env={'PYVO_TEST_NOW': now},
                                   obj=obj, input=stdin_text)
            if result.exc_info and not isinstance(result.exc_info[1], SystemExit):
                raise result.exc_info[1]
            print(result.output)
            return result
        finally:
            sys.stdin = prev_stdin

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
    result = run('show', 'brno', now='2012-11-29 12:00:00')
    assert result.exit_code == 0
    assert result.output == textwrap.dedent("""\
        2012-11-29 (Thursday, November 29, 2012) we're meeting at the Brno meetup

          Brněnské PyVo – CLI

            Python v příkazové řádce: od zpracování argumentů po barevné tabulky

        at U Dřeváka, Dřevařská 22, 602 00, Brno
          49.209095 N, 16.6008957 E
          http://mapy.cz/zakladni?x=16.6008957&y=49.209095&z=17

        Talks:
          Tomáš Ehrlich: Docopt
              Něco o docopt + malé shrnutí (arg|opt)parse
            http://lanyrd.com/2012/pyvo-november/sztmf/
            https://github.com/elvard/talks/blob/master/2012/2012-11-29-pyvo-cli/2012-11-29-pyvo-cli.pdf?raw=true
            https://github.com/elvard/talks/tree/master/2012/2012-11-29-pyvo-cli
            [>] http://www.youtube.com/watch?v=4AV7NyQj9ZY

          Petr Viktorin: Textová rozhraní
            http://lanyrd.com/2012/pyvo-november/scbfhh/
            https://github.com/encukou/slides/tree/master/2012-11-29-pyvo-cli
            [>] http://www.youtube.com/watch?v=Rzkv2uwjXAU

        More info online:
          http://lanyrd.com/2012/pyvo-november/
        """).expandtabs(4)


def test_show_no_upcoming(run, get_yaml_data):
    result = run('show', 'brno', now='2099-01-01 00:00:00')
    assert result.exit_code != 0
    assert result.output.strip() == 'No such meetup'


@pytest.mark.parametrize(['filename', 'args'], [
    ['series/brno-pyvo/events//2015-02-26*.yaml', ('brno', )],
    ['series/ostrava-pyvo/events/2013-12-04*.yaml', ('ostrava', 'p1')],
    ['series/ostrava-pyvo/events//2013-11-07*.yaml', ('ostrava', 'p2')],
    ['series/ostrava-pyvo/events//2014-08-07*.yaml', ('ostrava', '+1')],
    ['series/ostrava-pyvo/events//2014-10-02*.yaml', ('ostrava', '+2')],
    ['series/ostrava-pyvo/events//2014-11-06*.yaml', ('ostrava', '11')],
    ['series/ostrava-pyvo/events//2013-11-07*.yaml', ('ostrava', '13-11')],
    ['series/ostrava-pyvo/events//2013-11-07*.yaml', ('ostrava', '2013-11')],
    ['series/ostrava-pyvo/events//2013-11-07*.yaml', ('ostrava', '13-11-07')],
    ['series/ostrava-pyvo/events//2013-11-07*.yaml', ('ostrava', '2013-11-07')],
])
def test_show_event(run, get_yaml_data, args, filename):
    result = run('--yaml', 'show',  *args)
    assert result.exit_code == 0
    ysl = yaml.safe_load
    assert ysl(result.output) == ysl(get_yaml_data(filename))


@pytest.mark.parametrize(['message', 'args'], [
    ['No such meetup', ('brno', 'p100')],
    ['No such meetup', ('brno', '+1000')],
    ['No such meetup', ('brno', '1876-10')],
])
def test_show_event_negative(run, get_yaml_data, args, message):
    result = run('show',  *args)
    assert result.exit_code != 0
    assert result.output.strip() == message


def test_calendar(run):
    result = run('calendar')
    assert result.exit_code == 0
    assert result.output == textwrap.dedent("""\
        #         July                 August              September       #
        #       2014-07               2014-08               2014-09        #
        # Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su #
        #     1  2  3  4  5  6               1  2  3   1  2  3  4  5  6  7 #
        #  7  8  9 10 11 12 13   4  5  6[os] 8  9 10   8  9 10 11 12 13 14 #
        # 14 15 16 17 18 19 20  11 12 13 14 15 16 17  15 16 17 18 19 20 21 #
        # 21 22 23 24 25 26 27  18 19 20 21 22 23 24  22 23 24 25 26 27 28 #
        # 28 29 30 br           25 26 27 28 29 30 31  29 30                #
        #                                                                  #

        July:
        brno      2014-07-31 Brněnské Pyvo + BRUG – Bitva tří císařů

        August:
        ostrava   2014-08-07 Ostravské KinoPyvo
        """).replace('#', '')


def test_calendar_last_month(run):
    result = run('calendar', 'p1')
    assert result.exit_code == 0
    assert result.output == textwrap.dedent("""\
        #         June                  July                 August        #
        #       2014-06               2014-07               2014-08        #
        # Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su #
        #                    1      1  2  3  4  5  6               1  2  3 #
        #  2  3  4  5  6  7  8   7  8  9 10 11 12 13   4  5  6[os] 8  9 10 #
        #  9 10 11 12 13 14 15  14 15 16 17 18 19 20  11 12 13 14 15 16 17 #
        # 16 17 18 19 20 21 22  21 22 23 24 25 26 27  18 19 20 21 22 23 24 #
        # 23 24 25 26 27 28 29  28 29 30 br           25 26 27 28 29 30 31 #
        # 30                                                               #

        July:
        brno      2014-07-31 Brněnské Pyvo + BRUG – Bitva tří císařů

        August:
        ostrava   2014-08-07 Ostravské KinoPyvo
        """).replace('#', '')


def test_calendar_today_last_in_month(run):
    result = run('calendar', now='2014-08-31 12:00:00')
    assert result.exit_code == 0
    assert result.output == textwrap.dedent("""\
        #         July                 August              September       #
        #       2014-07               2014-08               2014-09        #
        # Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su #
        #     1  2  3  4  5  6               1  2  3   1  2  3  4  5  6  7 #
        #  7  8  9 10 11 12 13   4  5  6 os  8  9 10   8  9 10 11 12 13 14 #
        # 14 15 16 17 18 19 20  11 12 13 14 15 16 17  15 16 17 18 19 20 21 #
        # 21 22 23 24 25 26 27  18 19 20 21 22 23 24  22 23 24 25 26 27 28 #
        # 28 29 30 br           25 26 27 28 29 30[31] 29 30                #
        #                                                                  #

        July:
        brno      2014-07-31 Brněnské Pyvo + BRUG – Bitva tří císařů

        August:
        ostrava   2014-08-07 Ostravské KinoPyvo
        """).replace('#', '')


def test_calendar_january(run):
    result = run('calendar', now='2014-01-01 12:00:00')
    assert result.exit_code == 0
    assert result.output == textwrap.dedent("""\
        #       December              January               February       #
        #       2013-12               2014-01               2014-02        #
        # Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su #
        #                    1       [ 1] 2  3  4  5                  1  2 #
        #  2  3 os  5  6  7  8   6  7  8  9 10 11 12   3  4  5  6  7  8  9 #
        #  9 10 11 12 13 14 15  13 14 15 16 17 18 19  10 11 12 13 14 15 16 #
        # 16 17 18 19 20 21 22  20 21 22 23 24 25 26  17 18 19 20 21 22 23 #
        # 23 24 25 26 27 28 29  27 28 29 30 31        24 25 26 br 28       #
        # 30 31                                                            #

        December:
        ostrava   2013-12-04 Ostravské Pyvo – Druhé

        February:
        brno      2014-02-27 Brněnské Pyvo + BRUG – Výjezdové
        """).replace('#', '')


def test_calendar_year(run):
    result = run('calendar', '-y')
    assert result.exit_code == 0
    assert result.output == textwrap.dedent("""\
        #       January               February               March         #
        #       2014-01               2014-02               2014-03        #
        # Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su #
        #        1  2  3  4  5                  1  2                  1  2 #
        #  6  7  8  9 10 11 12   3  4  5  6  7  8  9   3  4  5  6  7  8  9 #
        # 13 14 15 16 17 18 19  10 11 12 13 14 15 16  10 11 12 13 14 15 16 #
        # 20 21 22 23 24 25 26  17 18 19 20 21 22 23  17 18 19 20 21 22 23 #
        # 27 28 29 30 31        24 25 26 br 28        24 25 26 27 28 29 30 #
        #                                             31                   #
        #        April                  May                   June         #
        #       2014-04               2014-05               2014-06        #
        # Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su #
        #     1  2  3  4  5  6            1  2  3  4                     1 #
        #  7  8  9 10 11 12 13   5  6  7  8  9 10 11   2  3  4  5  6  7  8 #
        # 14 15 16 17 18 19 20  12 13 14 15 16 17 18   9 10 11 12 13 14 15 #
        # 21 22 23 24 25 26 27  19 20 21 22 23 24 25  16 17 18 19 20 21 22 #
        # 28 29 30              26 27 28 29 30 31     23 24 25 26 27 28 29 #
        #                                             30                   #
        #         July                 August              September       #
        #       2014-07               2014-08               2014-09        #
        # Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su #
        #     1  2  3  4  5  6               1  2  3   1  2  3  4  5  6  7 #
        #  7  8  9 10 11 12 13   4  5  6[os] 8  9 10   8  9 10 11 12 13 14 #
        # 14 15 16 17 18 19 20  11 12 13 14 15 16 17  15 16 17 18 19 20 21 #
        # 21 22 23 24 25 26 27  18 19 20 21 22 23 24  22 23 24 25 26 27 28 #
        # 28 29 30 br           25 26 27 28 29 30 31  29 30                #
        #                                                                  #
        #       October               November              December       #
        #       2014-10               2014-11               2014-12        #
        # Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su #
        #        1 os  3  4  5                  1  2   1  2  3  4  5  6  7 #
        #  6  7  8  9 10 11 12   3  4  5 os  7  8  9   8  9 10 11 12 13 14 #
        # 13 14 15 16 17 18 19  10 11 12 13 14 15 16  15 16 17 18 19 20 21 #
        # 20 21 22 23 24 25 26  17 18 19 20 21 22 23  22 23 24 25 26 27 28 #
        # 27 28 29 30 31        24 25 26 27 28 29 30  29 30 31             #
        #                                                                  #
        """).replace('#', '')


def test_calendar_yaml(run):
    result = run('--yaml', 'calendar')
    assert result.exit_code == 0
    output = yaml.safe_load(result.output)
    assert output[0]
