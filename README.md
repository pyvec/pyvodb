This tool helps management of Pyvo meetups.

True to the readme-driven development style, this readme describes the
goals for the future, not the current state (use --help for that).

Format example: the file "praha/2014-09-17" could contain:

    start: 2014-09-17 19:00:00
    name: 'Pražské PyVo #42 work&travel'
    series: Pražské PyVo
    venue:
      city: Prague
      name: Na Věnečku
      address: "Ostrovského 38a, Praha 5, Czech Republic
      location:
        latitude: '50.0678996'
        longitude: '14.3953814'
    talks:
    - title: Startup in SF
      speakers:
      - Maksim Izmaylov
      urls:
      - http://lanyrd.com/2014/praha-pyvo-september/sddwfm/
    - title: Zabava s open-source
      speakers:
      - Honza Král
      urls:
      - http://lanyrd.com/2014/praha-pyvo-september/sddwfw/
    - title: Prace u more
      speakers:
      - Ales Zoulek
      urls:
      - http://lanyrd.com/2014/praha-pyvo-september/sddwgk/
    urls:
    - http://lanyrd.com/2014/praha-pyvo-september/


Usage:

*   `pyvo add <city> [date]`

    Opens an editor for the meetup at `date`, pre-filled using a template
    for `city`. (For now the templates are hard-coded Python.)
    After the editor is closed, save the file to the appropriate location
    (unless it's empty).

    If `date` is not given, *and* a meetup entry for `city` doesn't yet exist
    for the next month, pick the next usual date (defined in the template).

*   `pyvo mod <city> [date]`

    Opens an editor with the existing entry for `city` on `date`.

    The date can contain just a year and month, if that's not ambiguous;
    or it can be missing entirely, in which case it's the meetup for
    next month.

*   `pyvo del <city> [date]`

    Deletes the given entry. See `mod` for how date is treated)

*   `pyvo upload lanyrd <city> [<date>]`

    Creates a Lanyrd.com entry for the entry for `city` at `date` (see
    `mod` for how date is treated).

    Needs Lanyrd credentials configured. (TODO -- how?)


After using `pyvo` commands, you'll need to add the changes to git yourself.
