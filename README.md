This tool helps management of Pyvo meetups.

See https://github.com/pyvec/pyvo-data for an example of the "database"
this manages.


# Installation

Install with pip:

    pip install pyvodb

You'll probably also want to get some data to start with:

    git clone https://github.com/pyvec/pyvo-data

# Usage

Set the location of the Pyvo database:

    export PYVO_DATA=$PWD/pyvo-data

And then, you can query and modify the database:

*   `pyvo show <city> [date]`

    Show the entry in `city` for `date`.

    The date can contain just a year and month, if that's not ambiguous;
    or it can be missing entirely, in which case it's the upcoming meetup.
    See `pyvo show --help` for details.

*   `pyvo calendar`

    Show a pretty calendar of recent & upcoming meetups.

*   `pyvo edit <city> [date]`

    Opens an editor with the existing entry for `city` on `date`.

    (See `mod` for how date is treated)

*   `pyvo rm <city> [date]`

    Deletes the given entry.

    (See `show` for how date is treated)

*   `pyvo --help`, `pyvo COMMAND --help`

    Show all the options!

After using `pyvo` commands, you'll need to commit the changes to git yourself.

# Roadmap

*   `pyvo add <city> [date]`

    Opens an editor for a new meetup at `date`, pre-filled using a template
    for `city`. (Templates are hard-coded in Python, for now.)
    After the editor is closed, save the file to the appropriate location
    (unless it's empty).

    If `date` is not given, *and* a meetup entry for `city` doesn't yet exist
    for the next month, pick the next usual date (defined in a template).

*   `pyvo upload lanyrd <city> [<date>]`

    Creates a Lanyrd.com entry for the entry for `city` at `date`.
    (See `show` for how date is treated).

    Needs Lanyrd credentials configured. (TODO -- how?)

*   Stabilize and document the Python API

# Contribute

- Issue Tracker: github.com/pyvec/pyvodb/issues
- Source Code: github.com/pyvec/pyvodb

# Test

This project uses pytest for testing:

    pip install pytest
    py.test

The standard `python setup.py test` also works, but doesn't let you pass
useful options like `-v`.

# License

This code is under the MIT license
