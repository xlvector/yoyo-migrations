from datetime import datetime
from itertools import count
from logging import getLogger
import os
import sys
import inspect

from yoyo.compat import reraise, exec_, ustr
from yoyo.exceptions import DatabaseError
from yoyo.utils import plural

logger = getLogger(__name__)
default_migration_table = '_yoyo_migration'
_step_collectors = {}


def with_placeholders(conn, paramstyle, sql):
    placeholder_gen = {
        'qmark': '?',
        'format': '%s',
        'pyformat': '%s',
    }.get(paramstyle)
    if placeholder_gen is None:
        raise ValueError("Unsupported parameter format %s" % paramstyle)
    return sql.replace('?', placeholder_gen)


class Migration(object):

    def __init__(self, id, steps, source):
        self.id = id
        self.steps = steps
        self.source = source

    def isapplied(self, conn, paramstyle, migration_table):
        cursor = conn.cursor()
        try:
            cursor.execute(
                with_placeholders(conn, paramstyle, "SELECT COUNT(1) FROM " +
                                  migration_table + " WHERE id=?"),
                (self.id,)
            )
            return cursor.fetchone()[0] > 0
        finally:
            cursor.close()

    def apply(self, conn, paramstyle, migration_table, force=False):
        logger.info("Applying %s", self.id)
        Migration._process_steps(self.steps, conn, paramstyle, 'apply',
                                 force=force)
        cursor = conn.cursor()
        cursor.execute(
            with_placeholders(conn, paramstyle, "INSERT INTO " +
                              migration_table + " (id, ctime) VALUES (?, ?)"),
            (self.id, datetime.utcnow())
        )
        conn.commit()
        cursor.close()

    def rollback(self, conn, paramstyle, migration_table, force=False):
        logger.info("Rolling back %s", self.id)
        Migration._process_steps(reversed(self.steps), conn, paramstyle,
                                 'rollback', force=force)
        cursor = conn.cursor()
        cursor.execute(
            with_placeholders(conn, paramstyle, "DELETE FROM " +
                              migration_table + " WHERE id=?"),
            (self.id,)
        )
        conn.commit()
        cursor.close()

    @staticmethod
    def _process_steps(steps, conn, paramstyle, direction, force=False):

        reverse = {
            'rollback': 'apply',
            'apply': 'rollback',
        }[direction]

        executed_steps = []
        for step in steps:
            try:
                getattr(step, direction)(conn, paramstyle, force)
                executed_steps.append(step)
            except DatabaseError:
                conn.rollback()
                exc_info = sys.exc_info()
                try:
                    for step in reversed(executed_steps):
                        getattr(step, reverse)(conn, paramstyle)
                except DatabaseError:
                    logger.exception(
                        'Database error when reversing %s of step', direction)
                reraise(exc_info[0], exc_info[1], exc_info[2])


class PostApplyHookMigration(Migration):
    """
    A special migration that is run after successfully applying a set of
    migrations. Unlike a normal migration this will be run every time
    migrations are applied script is called.
    """

    def apply(self, conn, paramstyle, migration_table, force=False):
        logger.info("Applying %s", self.id)
        self.__class__._process_steps(
            self.steps,
            conn,
            paramstyle,
            'apply',
            force=True
        )

    def rollback(self, conn, paramstyle, migration_table, force=False):
        logger.info("Rolling back %s", self.id)
        self.__class__._process_steps(
            reversed(self.steps),
            conn,
            paramstyle,
            'rollback',
            force=True
        )


class StepBase(object):

    def apply(self, conn, paramstyle, force=False):
        raise NotImplementedError()

    def rollback(self, conn, paramstyle, force=False):
        raise NotImplementedError()


class Transaction(StepBase):
    """
    A ``Transaction`` object causes all associated steps to be run within a
    single database transaction.
    """

    def __init__(self, steps, ignore_errors=None):
        assert ignore_errors in (None, 'all', 'apply', 'rollback')
        self.steps = steps
        self.ignore_errors = ignore_errors

    def apply(self, conn, paramstyle, force=False):

        for step in self.steps:
            try:
                step.apply(conn, paramstyle, force)
            except DatabaseError:
                conn.rollback()
                if force or self.ignore_errors in ('apply', 'all'):
                    logger.exception("Ignored error in step %d", step.id)
                    return
                raise
        conn.commit()

    def rollback(self, conn, paramstyle, force=False):
        for step in reversed(self.steps):
            try:
                step.rollback(conn, paramstyle, force)
            except DatabaseError:
                conn.rollback()
                if force or self.ignore_errors in ('rollback', 'all'):
                    logger.exception("Ignored error in step %d", step.id)
                    return
                raise
        conn.commit()


class MigrationStep(StepBase):
    """
    Model a single migration.

    Each migration step comprises apply and rollback steps of up and down SQL
    statements.
    """

    transaction = None

    def __init__(self, id, apply, rollback):

        self.id = id
        self._rollback = rollback
        self._apply = apply

    def _execute(self, cursor, stmt, out=sys.stdout):
        """
        Execute the given statement. If rows are returned, output these in a
        tabulated format.
        """
        if isinstance(stmt, ustr):
            logger.debug(" - executing %r", stmt.encode('ascii', 'replace'))
        else:
            logger.debug(" - executing %r", stmt)
        cursor.execute(stmt)
        if cursor.description:
            result = [[ustr(value) for value in row]
                      for row in cursor.fetchall()]
            column_names = [desc[0] for desc in cursor.description]
            column_sizes = [len(c) for c in column_names]

            for row in result:
                for ix, value in enumerate(row):
                    if len(value) > column_sizes[ix]:
                        column_sizes[ix] = len(value)
            format = '|'.join(' %%- %ds ' % size for size in column_sizes)
            out.write(format % tuple(column_names) + "\n")
            out.write('+'.join('-' * (size + 2) for size in column_sizes)
                      + "\n")
            for row in result:
                out.write((format % tuple(row)).encode('utf8') + "\n")
            out.write(plural(len(result), '(%d row)', '(%d rows)') + "\n")

    def apply(self, conn, paramstyle, force=False):
        """
        Apply the step.

        :param force: If true, errors will be logged but not be re-raised
        """
        logger.info(" - applying step %d", self.id)
        if not self._apply:
            return
        cursor = conn.cursor()
        try:
            if isinstance(self._apply, (ustr, str)):
                self._execute(cursor, self._apply)
            else:
                self._apply(conn)
        finally:
            cursor.close()

    def rollback(self, conn, paramstyle, force=False):
        """
        Rollback the step.
        """
        logger.info(" - rolling back step %d", self.id)
        if self._rollback is None:
            return
        cursor = conn.cursor()
        try:
            if isinstance(self._rollback, (ustr, str)):
                self._execute(cursor, self._rollback)
            else:
                self._rollback(conn)
        finally:
            cursor.close()


def read_migrations(conn, paramstyle, directory, names=None,
                    migration_table=default_migration_table):
    """
    Return a ``MigrationList`` containing all migrations from ``directory``.
    If ``names`` is given, this only return migrations with names from the
    given list (without file extensions).
    """
    migrations = MigrationList(conn, paramstyle, migration_table)
    paths = [os.path.join(directory, path)
             for path in os.listdir(directory) if path.endswith('.py')]

    for path in sorted(paths):

        filename = os.path.splitext(os.path.basename(path))[0]

        if filename.startswith('post-apply'):
            migration_class = PostApplyHookMigration
        else:
            migration_class = Migration

        if migration_class is Migration and \
                names is not None and filename not in names:
            continue

        file = open(path, 'r')
        try:
            source = file.read()
            migration_code = compile(source, file.name, 'exec')
        finally:
            file.close()

        collector = _step_collectors[file.name] = StepCollector()
        ns = {'step': collector.step, 'transaction': collector.transaction}
        try:
            exec_(migration_code, ns)
        except Exception:
            logger.exception("Could not import migration from %r", path)
            continue
        migration = migration_class(os.path.basename(filename),
                                    collector.steps, source)
        if migration_class is PostApplyHookMigration:
            migrations.post_apply.append(migration)
        else:
            migrations.append(migration)

    return migrations


class MigrationList(list):
    """
    A list of database migrations.

    Use ``to_apply`` or ``to_rollback`` to retrieve subset lists of migrations
    that can be applied/rolled back.
    """

    def __init__(self, conn, paramstyle, migration_table, items=None,
                 post_apply=None):
        super(MigrationList, self).__init__(items if items else [])
        self.conn = conn
        self.paramstyle = paramstyle
        self.migration_table = migration_table
        self.post_apply = post_apply if post_apply else []
        initialize_connection(self.conn, migration_table)

    def to_apply(self):
        """
        Return a list of the subset of migrations not already applied.
        """
        return self.__class__(
            self.conn,
            self.paramstyle,
            self.migration_table,
            [m
             for m in self
             if not m.isapplied(self.conn, self.paramstyle,
                                self.migration_table)],
            self.post_apply
        )

    def to_rollback(self):
        """
        Return a list of the subset of migrations already applied, which may be
        rolled back.

        The order of migrations will be reversed.
        """
        return self.__class__(
            self.conn,
            self.paramstyle,
            self.migration_table,
            list(reversed([m
                           for m in self
                           if m.isapplied(self.conn, self.paramstyle,
                                          self.migration_table)])),
            self.post_apply
        )

    def filter(self, predicate):
        return self.__class__(
            self.conn,
            self.paramstyle,
            self.migration_table,
            [m for m in self if predicate(m)],
            self.post_apply
        )

    def replace(self, newmigrations):
        return self.__class__(self.conn, self.paramstyle, self.migration_table,
                              newmigrations, self.post_apply)

    def apply(self, force=False):
        if not self:
            return
        for m in self + self.post_apply:
            m.apply(self.conn, self.paramstyle, self.migration_table, force)

    def rollback(self, force=False):
        if not self:
            return
        for m in self + self.post_apply:
            m.rollback(self.conn, self.paramstyle, self.migration_table, force)

    def __getslice__(self, i, j):
        return self.__class__(
            self.conn,
            self.paramstyle,
            self.migration_table,
            super(MigrationList, self).__getslice__(i, j),
            self.post_apply
        )


def create_migrations_table(conn, tablename):
    """
    Create a database table to track migrations
    """
    try:
        cursor = conn.cursor()
        try:
            try:
                cursor.execute("""
                    CREATE TABLE %s (id VARCHAR(255) NOT NULL PRIMARY KEY,
                                     ctime TIMESTAMP)
                """ % (tablename,))
                conn.commit()
            except DatabaseError:
                pass
        finally:
            cursor.close()
    finally:
        conn.rollback()


def initialize_connection(conn, tablename):
    """
    Initialize the DBAPI connection for use.

    - Installs ``yoyo.excpetions.DatabaseError`` as a base class for the
      connection's own DatabaseError

    - Creates the migrations table if not already existing

    """
    module = inspect.getmodule(type(conn))
    if DatabaseError not in module.DatabaseError.__bases__:
        module.DatabaseError.__bases__ += (DatabaseError,)
    create_migrations_table(conn, tablename)


class StepCollector(object):
    """
    Provide the ``step`` and ``transaction`` functions used in migration
    scripts.

    Each call to step/transaction updates the StepCollector's ``steps`` list.
    """

    def __init__(self):
        self.steps = []
        self.step_id = count(0)

    def step(self, apply, rollback=None, ignore_errors=None):
        """
        Wrap the given apply and rollback code in a transaction, and add it
        to the list of steps.
        Return the transaction-wrapped step.
        """
        t = Transaction([MigrationStep(next(self.step_id), apply, rollback)],
                        ignore_errors)
        self.steps.append(t)
        return t

    def transaction(self, *steps, **kwargs):
        """
        Wrap the given list of steps in a single transaction, removing the
        default transactions around individual steps.
        """
        ignore_errors = kwargs.pop('ignore_errors', None)
        assert kwargs == {}

        transaction = Transaction([], ignore_errors)
        for oldtransaction in steps:
            if oldtransaction.ignore_errors is not None:
                raise AssertionError("ignore_errors cannot be specified "
                                        "within a transaction")
            try:
                (step,) = oldtransaction.steps
            except ValueError:
                raise AssertionError("Transactions cannot be nested")
            transaction.steps.append(step)
            self.steps.remove(oldtransaction)
        self.steps.append(transaction)
        return transaction


def step(*args, **kwargs):
    fi = inspect.getframeinfo(inspect.stack()[1][0])
    return _step_collectors[fi.filename].step(*args, **kwargs)


def transaction(*args, **kwargs):
    fi = inspect.getframeinfo(inspect.stack()[1][0])
    return _step_collectors[fi.filename].transaction(*args, **kwargs)
