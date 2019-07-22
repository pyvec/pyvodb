## 1.0 (2019-07-22)

* Release with updated dependencies
* Add videometadata exporter
* Use better regexp for YouTube video id

## 0.3 (2016-10-16)

* Removed CLI editing support; the database is now load-only. This simplifies
  loading significantly.
* Switched to "version 2" of the YAML schema.
  This version treats cities and venues as separate objects,
  and adds additional metatada to them.
  Also, Series are added in preparation for supporting more event series
  in one city.
* Added a mechanism to get probable dates for upcoming meetups, even if
  they haven't been planned yet, through RFC 2445 recurrence rules

## 0.2 (2015-09-06)

* Recognize `https` Youtube links
* Support Python 3.3

## 0.1

* Initial release

