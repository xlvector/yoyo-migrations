CHANGELOG
---------

Version 4.2.4

* Fix for mismanaged 4.2.3 release

Version 4.2.3

* Migrations are now datestamped with a UTC date (thanks to robi wan)

* Fixes for installation and use under python 3

Version 4.2.2

* Migration scripts can start with ``from yoyo import step, transaction``.
  This prevents linters (eg flake8) throwing errors over undefined names.

* Bugfix: functions declared in a migration file can access the script's global
  namespace

Version 4.2.1

* Bugfix for previous release, which omitted critical files

Version 4.2.0

* Removed yoyo.migrate namespace package. Any code that uses the yoyo api
  directly needs have any imports modified, eg this::

    from yoyo.migrate import read_migrations
    from yoyo.migrate.connections import connect

  Should be changed to this::

    from yoyo import read_migrations
    from yoyo.connections import connect

* Migrated from darcs to mercurial. Code is now hosted at
  https://bitbucket.org/ollyc/yoyo

* Bugfix: the migration_table option was not being passed to read_migrations,
  causing the value to be ignored

Version 4.1.6

* Added windows support (thanks to Peter Shinners)

Version 4.1.5

* Configure logging handlers so that the -v switch causes output to go to the
  console (thanks to Andrew Nelis).

* ``-v`` command line switch no longer takes an argument but may be specified
  multiple times instead (ie use ``-vvv`` instead of ``-v3``). ``--verbosity``
  retains the old behaviour.

Version 4.1.4

* Bugfix for post apply hooks

Version 4.1.3

* Changed default migration table name back to '_yoyo_migration'

Version 4.1.2

* Bugfix for error when running in interactive mode

Version 4.1.1

* Introduced configuration option for migration table name

Version 4.1.0

* Introduced ability to run steps within a transaction (thanks to Ryan Williams
  for suggesting this functionality along with assorted bug fixes.)

* "post-apply" migrations can be run after every successful upward migration

* Other minor bugfixes and improvements

* Switched to <major>.<minor> version numbering convention

Version 4

* Fixed problem installing due to missing manifest entry

Version 3

* Use the console_scripts entry_point in preference to scripts=[] in
  setup.py, this provides better interoperability with buildout

Version 2

* Fixed error when reading dburi from config file

Version 1

* Initial release

