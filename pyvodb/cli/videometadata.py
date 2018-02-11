import os.path
from collections import OrderedDict
import yaml
import click

from slugify import slugify
from pyvodb.cli.top import cli
from pyvodb.cli import cliutil


yaml.SafeDumper.add_representer(OrderedDict,
    lambda dumper, value: dumper.represent_dict(value.items()))


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
    print(evdir)
    print()

    if event.talks:
        talknum = 1
        for talk in event.talks:
            config = OrderedDict()
            config['speaker'] = ', '.join(s.name for s in talk.speakers)
            config['title'] = talk.title
            config['lightning'] = talk.is_lightning
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
            confyaml = yaml.safe_dump(config, default_flow_style=False,
                                      allow_unicode=True)
            talkdir = "{:02d}-{}".format(talknum, slugify(talk.title))
            print(talkdir)
            print(confyaml)
            talknum += 1
            p = os.path.join(outpath, evdir, talkdir)
            if not os.path.exists(p):
                os.makedirs(p)
            with open(os.path.join(p, 'config.yaml'), 'w') as outf:
                outf.write(confyaml)
