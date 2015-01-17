from yoyo.connections import parse_uri, unparse_uri


def _test_parse_uri(connection_string, expected_uri_tuple):
    uri_tuple = parse_uri(connection_string)
    assert isinstance(uri_tuple, tuple)
    assert (uri_tuple == expected_uri_tuple)


def _test_unparse_uri(uri_tuple, expected_connection_string):
    connection_string = unparse_uri(uri_tuple)
    assert isinstance(connection_string, str)
    assert (connection_string == expected_connection_string)


def test_uri_without_db_params():
    connection_string = 'postgres://user:password@server:7777/database'
    uri_tuple = ('postgres', 'user', 'password', 'server', 7777, 'database', None)
    _test_parse_uri(connection_string, uri_tuple)
    _test_unparse_uri(uri_tuple, connection_string)


def test_parse_uri_with_db_params():
    connection_string = 'odbc://user:password@server:7777/database?DSN=dsn'
    uri_tuple = ('odbc', 'user', 'password', 'server', 7777, 'database', {'DSN': 'dsn'})
    _test_parse_uri(connection_string, uri_tuple)
    _test_unparse_uri(uri_tuple, connection_string)
