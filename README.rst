Yoyo database migrations
========================

Yoyo is a database schema migration tool using plain SQL and python's builtin
DB-API.

What does yoyo-migrations do?
-----------------------------

As database applications evolve, changes to the database schema are often
required. These can usually be written as one-off SQL scripts containing
CREATE/ALTER table statements (although any SQL or python script may be used
with yoyo).

Yoyo provides a command line tool for reading a directory of such
scripts and applying them to your database as required.

Installation
------------

Install from the PyPI with the command::

  pip install yoyo-migrations

Database support
----------------

PostgreSQL, MySQL, ODBC and SQLite databases are supported.


Usage
-----

Yoyo is usually invoked as a command line script.

Examples:

Read all migrations from directory ``migrations`` and apply them to a
PostgreSQL database::

   yoyo-migrate apply ./migrations/ postgres://user:password@localhost/database

Rollback migrations previously applied to a MySQL database::

   yoyo-migrate rollback ./migrations/ mysql://user:password@localhost/database

Reapply (ie rollback then apply again) migrations to a SQLite database at
location ``/home/sheila/important-data.db``::

    yoyo-migrate reapply ./migrations/ sqlite:////home/sheila/important-data.db

By default, yoyo-migrations starts in an interactive mode, prompting you for
each migration file before applying it, making it easy to choose which
migrations to apply and rollback.

The migrations directory should contain a series of migration scripts. Each
migration script is a python file (``.py``) containing a series of steps. Each
step should comprise a migration query and (optionally) a rollback query. For
example::

    #
    # file: migrations/0001.create-foo.py
    #
    from yoyo import step
    step(
        "CREATE TABLE foo (id INT, bar VARCHAR(20), PRIMARY KEY (id))",
        "DROP TABLE foo",
    )

The filename of each file (without the .py extension) is used as the identifier
for each migration. Migrations are applied in filename order, so it's useful to
name your files using a date (eg '20090115-xyz.py') or some other incrementing
number.

yoyo-migrate creates a table in your target database, ``_yoyo_migration``, to
track which migrations have been applied.

Steps may also take an optional argument ``ignore_errors``, which must be one
of ``apply``, ``rollback``, or ``all``. If in the previous example the table
foo might have already been created by another means, we could add
``ignore_errors='apply'`` to the step to allow the migrations to continue
regardless::

    #
    # file: migrations/0001.create-foo.py
    #
    from yoyo import step
    step(
        "CREATE TABLE foo (id INT, bar VARCHAR(20), PRIMARY KEY (id))",
        "DROP TABLE foo",
        ignore_errors='apply',
    )

Steps can also be python callable objects that take a database connection as
their single argument. For example::

    #
    # file: migrations/0002.update-keys.py
    #
    from yoyo import step
    def do_step(conn):
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sysinfo "
            " (osname, hostname, release, version, arch)"
            " VALUES (%s, %s, %s, %s, %s %s)",
            os.uname()
        )

    step(do_step)

Transactions
------------

By default each step is run in its own transaction.
You can run multiple steps within a single transaction by wrapping them in a
``transaction`` call, like so::

  #
  # file: migrations/0001.create-foo.py
  #
  from yoyo import step, transaction
  transaction(
    step(
      "CREATE TABLE foo (id INT, bar VARCHAR(20), PRIMARY KEY (id))",
      "DROP TABLE foo",
    ),
    step("INSERT INTO foo (1, 'baz')"),
    ignore_errors='all',
  )

If this is the case setting ``ignore_errors`` on individual steps makes no
sense: database errors will always cause the entire transaction to be rolled
back. The outer ``transaction`` can however have ``ignore_errors`` set.

Post-apply hook
---------------

It can be useful to have a script that's run after successful migrations. For
example you could use this to update database permissions or re-create views.
To do this, create a migration file called ``post-apply.py``. This file should
have the same format as any other migration file.

Password security
-----------------

You normally specify your database username and password as part of the
database connection string on the command line. On a multi-user machine, other
users could view your database password in the process list.

The ``-p`` or ``--prompt-password`` flag causes yoyo-migrate to prompt
for a password, ignoring any password specified in the connection string. This
password will not be available to other users via the system's process list.

Connection string caching
-------------------------

The first time you run ``yoyo-migrate`` on a new set of migrations, you will be
asked if you want to cache the database connection string in a file
called ``.yoyo-migrate`` in the migrations directory.

This cache is local to the migrations directory, so subsequent runs
on the same migration set do not need the database connection string to be
specified.

This saves typing, avoids your database username and password showing in
process listings and lessens the risk of accidentally running ``yoyo-migrate``
on the wrong database (ie by re-running an earlier ``yoyo-migrate`` entry in
your command history when you have moved to a different directory).

If you do not want this cache file to be used, add the ``--no-cache`` parameter
to the command line options.

Using yoyo from python code
---------------------------

The following example shows how to apply migrations from inside python code::

    from yoyo import read_migrations
    from yoyo.connections import connect

    conn, paramstyle = connect('postgres://myuser@localhost/mydatabase')
    migrations = read_migrations(conn, paramstyle, 'path/to/migrations'))
    migrations.to_apply().apply()
    conn.commit()

.. :vim:sw=4:et
