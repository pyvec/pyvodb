import os.path
from collections import OrderedDict
import click

from slugify import slugify
from pyvodb.cli.top import cli
from pyvodb.cli import cliutil
from pyvodb.dumpers import yaml_dump


def cfgdump(path, config):
    """Create output directory path and output there the config.yaml file."""
    dump = yaml_dump(config)
    if not os.path.exists(path):
        os.makedirs(path)
    with open(os.path.join(path, 'config.yaml'), 'w') as outf:
        outf.write(dump)
    print(dump)


@cli.command()
@click.argument('city')
@click.argument('date')
@click.argument('outpath', default=".")
@click.pass_context
def videometadata(ctx, city, date, outpath):
    """Generate metadata for video records.

    city: The meetup series.

    \b
    date: The date. May be:
        - YYYY-MM-DD or YY-MM-DD (e.g. 2015-08-27)
        - YYYY-MM or YY-MM (e.g. 2015-08)
        - MM (e.g. 08): the given month in the current year
        - pN (e.g. p1): show the N-th last meetup
    """
    db = ctx.obj['db']
    today = ctx.obj['now'].date()

    event = cliutil.get_event(db, city, date, today)

    data = event.as_dict()
    cliutil.handle_raw_output(ctx, data)

    evdir = "{}-{}".format(event.city.name, event.slug)

    config = OrderedDict()
    config['speaker'] = ''
    config['title'] = ''
    config['lightning'] = True
    config['speaker_only'] = False
    config['widescreen'] = False
    config['speaker_vid'] = "*.MTS"
    config['screen_vid'] = "*.ts"
    config['event'] = event.name
    if event.number:
        config['event'] += " #{}".format(event.number)
    config['date'] = event.date.strftime("%Y-%m-%d")
    config['url'] = "https://pyvo.cz/{}/{}/".format(event.series_slug,
                                                    event.slug)

    print(evdir)
    cfgdump(os.path.join(outpath, evdir), config)

    if event.talks:
        for talknum, talk in enumerate(event.talks, start=1):
            config['speaker'] = ', '.join(s.name for s in talk.speakers)
            config['title'] = talk.title
            config['lightning'] = talk.is_lightning
            talkdir = "{:02d}-{}".format(talknum, slugify(talk.title))
            print(talkdir)
            cfgdump(os.path.join(outpath, evdir, talkdir), config)
