import os.path

from mock import patch, call

from yoyo.tests import with_migrations, dburi
from yoyo.scripts.migrate import main


class TestYoyoScript(object):

    def setup(self):
        self.prompt_patch = patch('yoyo.scripts.migrate.prompt',
                                  return_value='n')
        self.prompt = self.prompt_patch.start()

    def teardown(self):
        self.prompt_patch.stop()

    @with_migrations()
    def test_it_sets_verbosity_level(self, tmpdir):
        with patch('yoyo.scripts.migrate.configure_logging') as m:
            main(['apply', tmpdir, dburi])
            assert m.call_args == call(0)
            main(['-vvv', 'apply', tmpdir, dburi])
            assert m.call_args == call(3)

    @with_migrations()
    def test_it_prompts_to_cache_connection_params(self, tmpdir):
        main(['apply', tmpdir, dburi])
        assert 'save connection string' in self.prompt.call_args[0][0].lower()

    @with_migrations()
    def test_it_caches_connection_params(self, tmpdir):
        self.prompt.return_value = 'y'
        main(['apply', tmpdir, dburi])
        assert os.path.exists(os.path.join(tmpdir, '.yoyo-migrate'))
        with open(os.path.join(tmpdir, '.yoyo-migrate')) as f:
            assert 'dburi = {0}'.format(dburi) in f.read()

    @with_migrations()
    def test_it_prompts_migrations(self, tmpdir):
        with patch('yoyo.scripts.migrate.read_migrations') as read_migrations:
            with patch('yoyo.scripts.migrate.prompt_migrations') \
                    as prompt_migrations:
                main(['apply', tmpdir, dburi])
                migrations = read_migrations().to_apply()
                assert migrations in prompt_migrations.call_args[0]

    @with_migrations()
    def test_it_applies_migrations(self, tmpdir):
        with patch('yoyo.scripts.migrate.read_migrations') as read_migrations:
            main(['-b', 'apply', tmpdir, dburi])
            migrations = read_migrations().to_apply()
            assert migrations.rollback.call_count == 0
            assert migrations.apply.call_count == 1

    @with_migrations()
    def test_it_rollsback_migrations(self, tmpdir):
        with patch('yoyo.scripts.migrate.read_migrations') as read_migrations:
            main(['-b', 'rollback', tmpdir, dburi])
            migrations = read_migrations().to_rollback()
            assert migrations.rollback.call_count == 1
            assert migrations.apply.call_count == 0

    @with_migrations()
    def test_it_reapplies_migrations(self, tmpdir):
        with patch('yoyo.scripts.migrate.read_migrations') as read_migrations:
            main(['-b', 'reapply', tmpdir, dburi])
            migrations = read_migrations().to_rollback()
            assert migrations.rollback.call_count == 1
            assert migrations.apply.call_count == 1
