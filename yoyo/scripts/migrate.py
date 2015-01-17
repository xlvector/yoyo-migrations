#!/usr/bin/env python
from __future__ import print_function
import logging
import argparse
import os
import re
import sys
try:
    from configparser import ConfigParser, NoSectionError, NoOptionError
except ImportError:
    from ConfigParser import ConfigParser, NoSectionError, NoOptionError  # noqa

from getpass import getpass

from yoyo.connections import connect, parse_uri, unparse_uri
from yoyo.utils import prompt, plural
from yoyo import read_migrations, default_migration_table
from yoyo import logger

verbosity_levels = {
    0: logging.ERROR,
    1: logging.WARN,
    2: logging.INFO,
    3: logging.DEBUG
}


def readconfig(path):
    config = ConfigParser()
    config.read([path])
    return config


def saveconfig(config, path):
    os.umask(0o77)
    f = open(path, 'w')
    try:
        return config.write(f)
    finally:
        f.close()


class prompted_migration(object):

    def __init__(self, migration, default=None):
        super(prompted_migration, self).__init__()
        self.migration = migration
        self.choice = default


def prompt_migrations(conn, paramstyle, migrations, direction):
    """
    Iterate through the list of migrations and prompt the user to
    apply/rollback each. Return a list of user selected migrations.

    direction
        one of 'apply' or 'rollback'
    """
    migrations = migrations.replace(prompted_migration(m) for m in migrations)

    position = 0
    while position < len(migrations):
        mig = migrations[position]

        choice = mig.choice
        if choice is None:
            isapplied = mig.migration.isapplied(conn, paramstyle,
                                                migrations.migration_table)
            if direction == 'apply':
                choice = 'n' if isapplied else 'y'
            else:
                choice = 'y' if isapplied else 'n'
        options = ''.join(o.upper() if o == choice else o.lower()
                          for o in 'ynvdaqjk?')

        print("")
        print('[%s]' % (mig.migration.id,))
        response = prompt("Shall I %s this migration?" % (direction,), options)

        if response == '?':
            print("")
            print("y: %s this migration" % (direction,))
            print("n: don't %s it" % (direction,))
            print("")
            print("v: view this migration in full")
            print("")
            print("d: %s the selected migrations, skipping any remaining" %
                    (direction,))
            print("a: %s all the remaining migrations" % (direction,))
            print("q: cancel without making any changes")
            print("")
            print("j: skip to next migration")
            print("k: back up to previous migration")
            print("")
            print("?: show this help")
            continue

        if response in 'yn':
            mig.choice = response
            position += 1
            continue

        if response == 'v':
            print(mig.migration.source)
            continue

        if response == 'j':
            position = min(len(migrations), position + 1)
            continue

        if response == 'k':
            position = max(0, position - 1)

        if response == 'd':
            break

        if response == 'a':
            for mig in migrations[position:]:
                mig.choice = 'y'
            break

        if response == 'q':
            for mig in migrations:
                mig.choice = 'n'
            break

    return migrations.replace(m.migration
                              for m in migrations
                              if m.choice == 'y')


def make_argparser():

    min_verbosity = min(verbosity_levels)
    max_verbosity = max(verbosity_levels)

    argparser = argparse.ArgumentParser()
    argparser.add_argument("command", choices=['apply', 'rollback', 'reapply'])
    argparser.add_argument("migrations_dir",
                           help="Directory containing migration scripts")
    argparser.add_argument("database", nargs="?", default=None,
                           help="Database, eg 'sqlite:///path/to/sqlite.db' "
                                "or 'postgresql://user@host/db'")

    argparser.add_argument("-m", "--match",
                           help="Select migrations matching PATTERN "
                            "(perl-compatible regular expression)",
                           metavar='PATTERN')
    argparser.add_argument("-a", "--all", dest="all", action="store_true",
                           help="Select all migrations, regardless of whether "
                                "they have been previously applied")
    argparser.add_argument("-b", "--batch", dest="batch", action="store_true",
                           help="Run in batch mode (don't ask before "
                                "applying/rolling back each migration)")
    argparser.add_argument("-v", dest="verbose", action="count",
                           default=min_verbosity,
                           help="Verbose output. Use multiple times "
                                "to increase level of verbosity")
    argparser.add_argument("--verbosity", dest="verbosity_level",
                           type=int, default=min_verbosity,
                           help="Set verbosity level (%d-%d)" %
                                (min_verbosity, max_verbosity))
    argparser.add_argument("-f", "--force", dest="force", action="store_true",
                           help="Force apply/rollback of steps even if "
                                "previous steps have failed")
    argparser.add_argument("-p", "--prompt-password", dest="prompt_password",
                           action="store_true",
                           help="Prompt for the database password")
    argparser.add_argument("--no-cache", dest="cache", action="store_false",
                           default=True,
                           help="Don't cache database login credentials")
    argparser.add_argument("--migration-table", dest="migration_table",
                           action="store", default=None,
                           help="Name of table to use for storing "
                                "migration metadata")

    return argparser


def configure_logging(level):
    """
    Configure the python logging module with the requested loglevel
    """
    logging.basicConfig(level=verbosity_levels[level])


def main(argv=None):

    argparser = make_argparser()
    args = argparser.parse_args(argv)

    if args.verbosity_level:
        verbosity_level = args.verbosity_level
    else:
        verbosity_level = args.verbose
    verbosity_level = min(verbosity_level, max(verbosity_levels))
    verbosity_level = max(verbosity_level, min(verbosity_levels))
    configure_logging(verbosity_level)

    command = args.command
    migrations_dir = os.path.normpath(os.path.abspath(args.migrations_dir))
    dburi = args.database

    config_path = os.path.join(migrations_dir, '.yoyo-migrate')
    config = readconfig(config_path)

    if dburi is None and args.cache:
        try:
            logger.debug("Looking up connection string for %r", migrations_dir)
            dburi = config.get('DEFAULT', 'dburi')
        except (ValueError, NoSectionError, NoOptionError):
            pass

    if args.migration_table:
        migration_table = args.migration_table
    else:
        try:
            migration_table = config.get('DEFAULT', 'migration_table')
        except (ValueError, NoSectionError, NoOptionError):
            migration_table = None

    # Earlier versions had a bug where the migration_table could be set to the
    # string 'None'.
    if migration_table in (None, 'None'):
        migration_table = default_migration_table

    config.set('DEFAULT', 'migration_table', migration_table)

    if dburi is None:
        argparser.error(
            "Please specify command, migrations directory and "
            "database connection string arguments"
        )

    if args.prompt_password:
        password = getpass('Password for %s: ' % dburi)
        scheme, username, _, host, port, database, db_params = parse_uri(dburi)
        dburi = unparse_uri((scheme, username, password, host, port, database, db_params))

    # Cache the database this migration set is applied to so that subsequent
    # runs don't need the dburi argument. Don't cache anything in batch mode -
    # we can't prompt to find the user's preference.
    if args.cache and not args.batch:
        if not config.has_option('DEFAULT', 'dburi'):
            response = prompt(
                "Save connection string to %s for future migrations?\n"
                "This is saved in plain text and "
                "contains your database password." % (config_path,),
                "yn"
            )
            if response == 'y':
                config.set('DEFAULT', 'dburi', dburi)

        elif config.get('DEFAULT', 'dburi') != dburi:
            response = prompt(
                "Specified connection string differs from that saved in %s. "
                "Update saved connection string?" % (config_path,),
                "yn"
            )
            if response == 'y':
                config.set('DEFAULT', 'dburi', dburi)

        config.set('DEFAULT', 'migration_table', migration_table)
        saveconfig(config, config_path)

    conn, paramstyle = connect(dburi)

    migrations = read_migrations(conn, paramstyle, migrations_dir,
                                 migration_table=migration_table)

    if args.match:
        migrations = migrations.filter(
            lambda m: re.search(args.match, m.id) is not None)

    if not args.all:
        if command in ['apply']:
            migrations = migrations.to_apply()

        elif command in ['reapply', 'rollback']:
            migrations = migrations.to_rollback()

    if not args.batch:
        migrations = prompt_migrations(conn, paramstyle, migrations, command)

    if not args.batch and migrations:
        if prompt(command.title() +
                  plural(len(migrations), " %d migration", " %d migrations") +
                  " to %s?" % dburi, "Yn") != 'y':
            return 0

    if command == 'reapply':
        migrations.rollback(args.force)
        migrations.apply(args.force)

    elif command == 'apply':
        migrations.apply(args.force)

    elif command == 'rollback':
        migrations.rollback(args.force)

if __name__ == "__main__":
    main(sys.argv[1:])
