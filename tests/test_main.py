# tests/test_main.py
import sys
import os

# Add the project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest
from unittest.mock import AsyncMock, MagicMock

# Assuming main.py is in the project root /Users/pedrlima/projects/meli/mcps/fury_mysql-mcp/
# and pytest is run from there. This import might need adjustment based on your project structure.
import main as main_module

@pytest.fixture
def mock_db_objects():
    # 1. Cursor object (mock_cur)
    mock_cur = AsyncMock()
    mock_cur.fetchone = AsyncMock() # Individual methods need to be AsyncMock if awaited
    mock_cur.fetchall = AsyncMock()
    mock_cur.execute = AsyncMock()

    # 2. Async Context Manager for cursor (cursor_acm)
    # This is what `conn.cursor()` returns.
    cursor_acm = AsyncMock() # This object itself is the async context manager
    # When `async with cursor_acm as cur_obj:`, cur_obj will be the result of awaiting __aenter__
    cursor_acm.__aenter__.return_value = mock_cur
    # __aexit__ can be an AsyncMock too if its result/await status matters
    cursor_acm.__aexit__ = AsyncMock(return_value=None) 

    # 3. Connection object (mock_conn)
    mock_conn = AsyncMock()
    # conn.cursor() is a synchronous method in aiomysql that returns an async context manager.
    # So, mock_conn.cursor should be a MagicMock whose return_value is our cursor_acm.
    mock_conn.cursor = MagicMock(return_value=cursor_acm)

    # 4. Async Context Manager for connection (acquire_acm)
    # This is what `db_pool.acquire()` returns.
    acquire_acm = AsyncMock() # This object itself is the async context manager
    acquire_acm.__aenter__.return_value = mock_conn
    acquire_acm.__aexit__ = AsyncMock(return_value=None)

    # 5. DB Pool object (mock_db_pool)
    # aiomysql.Pool.acquire() is a synchronous method.
    mock_db_pool = MagicMock() 
    mock_db_pool.acquire = MagicMock(return_value=acquire_acm)
    
    return mock_db_pool, mock_conn, mock_cur

@pytest.fixture
def mock_ctx(mock_db_objects):
    mock_db, _, _ = mock_db_objects
    ctx = MagicMock() # Using generic MagicMock for simplicity
    ctx.request_context = MagicMock()
    ctx.request_context.lifespan_context = MagicMock()
    ctx.request_context.lifespan_context.db = mock_db
    return ctx

# Tests for health_check
@pytest.mark.asyncio
async def test_health_check_ok(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    mock_cur.fetchone.return_value = (1,) # Simulate DB returning a row for "SELECT 1"
    
    result = await main_module.health_check(mock_ctx)
    
    mock_cur.execute.assert_called_once_with("SELECT 1")
    assert result == {"status": "healthy", "database": "connected", "result": 1}

@pytest.mark.asyncio
async def test_health_check_fail_db_error(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    mock_cur.execute.side_effect = Exception("DB error") # Simulate a database error

    # The function should catch the exception and return an error dictionary
    result = await main_module.health_check(mock_ctx)
    assert result == {"status": "error", "error": "Service unavailable"}
    # Optionally, you can also check if logger.error was called if you mock the logger
    # For now, we'll assume the internal logging is correct based on the function's code.

# Tests for list_tables
@pytest.mark.asyncio
async def test_list_tables_success(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    mock_cur.fetchall.return_value = [('table1',), ('table2',)]
    
    result = await main_module.list_tables(mock_ctx)
    
    mock_cur.execute.assert_called_once_with("SHOW TABLES")
    assert result == [{"tablename": "table1"}, {"tablename": "table2"}]

@pytest.mark.asyncio
async def test_list_tables_empty(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    mock_cur.fetchall.return_value = []
    
    result = await main_module.list_tables(mock_ctx)
    
    assert result == []

# Tests for get_table_schema
@pytest.mark.asyncio
async def test_get_table_schema_success(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    # Simulate output from aiomysql.DictCursor for DESCRIBE
    mock_cur.fetchall.return_value = [
        {"Field": "id", "Type": "int(11)", "Null": "NO", "Key": "PRI", "Default": None, "Extra": "auto_increment"},
        {"Field": "name", "Type": "varchar(255)", "Null": "YES", "Key": "", "Default": None, "Extra": ""}
    ]
    table_name = "my_table"
    
    result = await main_module.get_table_schema(mock_ctx, table_name)
    
    mock_cur.execute.assert_called_once_with(f"DESCRIBE {table_name}")
    expected_result = [
        {"column_name": "id", "data_type": "int(11)"},
        {"column_name": "name", "data_type": "varchar(255)"}
    ]
    assert result == expected_result

# Tests for get_table_data
@pytest.mark.asyncio
async def test_get_table_data_success_select(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    mock_data = [{"id": 1, "value": "data1"}, {"id": 2, "value": "data2"}]
    mock_cur.fetchall.return_value = mock_data
    query = "SELECT * FROM test_table"
    
    result = await main_module.get_table_data(mock_ctx, query)
    
    mock_cur.execute.assert_called_once_with(query)
    assert result == mock_data

@pytest.mark.asyncio
async def test_get_table_data_non_select_query(mock_ctx):
    query = "UPDATE test_table SET value = 'new_data' WHERE id = 1"
    
    result = await main_module.get_table_data(mock_ctx, query)
    
    assert result == {"error": "You can only perform SELECT queries"}

@pytest.mark.asyncio
async def test_get_table_data_select_empty(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    mock_cur.fetchall.return_value = []
    query = "SELECT * FROM empty_table"

    result = await main_module.get_table_data(mock_ctx, query)
    mock_cur.execute.assert_called_once_with(query)
    assert result == []


# Tests for show_indexes_table
@pytest.mark.asyncio
async def test_show_indexes_table_success(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    # Simulate output from aiomysql.DictCursor for SHOW INDEX
    mock_cur.fetchall.return_value = [
        {"Table": "coupons", "Non_unique": 0, "Key_name": "PRIMARY", "Seq_in_index": 1, "Column_name": "id", "Collation": "A"},
        {"Table": "coupons", "Non_unique": 1, "Key_name": "batch_id_index", "Seq_in_index": 1, "Column_name": "batch_id", "Collation": "A"},
        {"Table": "coupons", "Non_unique": 0, "Key_name": "payment_id_installment", "Seq_in_index": 1, "Column_name": "payment_id", "Collation": "A"},
        {"Table": "coupons", "Non_unique": 0, "Key_name": "payment_id_installment", "Seq_in_index": 2, "Column_name": "current_installment", "Collation": "A"}
    ]
    table_name = "coupons"
    
    result = await main_module.show_indexes_table(mock_ctx, table_name)
    
    mock_cur.execute.assert_called_once_with(f"SHOW INDEX FROM {table_name}")
    expected_result = [
        {"index_name": "PRIMARY", "columns": ["id"]},
        {"index_name": "batch_id_index", "columns": ["batch_id"]},
        {"index_name": "payment_id_installment", "columns": ["payment_id", "current_installment"]}
    ]
    
    # Check that all expected items are present in the result, allowing for different order
    assert len(result) == len(expected_result)
    for res_item in result:
        assert any(exp_item['index_name'] == res_item['index_name'] and 
                   sorted(exp_item['columns']) == sorted(res_item['columns']) 
                   for exp_item in expected_result)


# Tests for get_db_pool
@pytest.mark.asyncio
async def test_get_db_pool_success(monkeypatch, mocker):
    # Ensure db_pool is None at the start of the test
    main_module.db_pool = None

    # Mock global database configuration constants in main_module
    mocker.patch.object(main_module, 'DATABASE_HOST', 'localhost_mock')
    mocker.patch.object(main_module, 'DATABASE_USER', 'testuser_mock')
    mocker.patch.object(main_module, 'DATABASE_PASSWORD', 'testpass_mock')
    mocker.patch.object(main_module, 'DATABASE_NAME', 'testdb_mock')
    mocker.patch.object(main_module, 'DATABASE_PORT', 3307) # Use a different port for mock

    # Mock aiomysql.create_pool
    mock_create_pool = mocker.patch('aiomysql.create_pool', new_callable=AsyncMock)
    mock_pool_instance = AsyncMock()
    mock_create_pool.return_value = mock_pool_instance

    pool = await main_module.get_db_pool()

    mock_create_pool.assert_called_once_with(
        host="localhost_mock",
        user="testuser_mock",
        password="testpass_mock",
        db="testdb_mock",
        port=3307,
        autocommit=False, # As per main.py
        # loop=mocker.ANY # aiomysql.create_pool uses asyncio.get_event_loop() by default if None
    )
    assert pool == mock_pool_instance
    assert main_module.db_pool == mock_pool_instance # Check global var assignment

@pytest.mark.asyncio
async def test_get_db_pool_missing_env_var(monkeypatch, mocker):
    # Ensure db_pool is None at the start of the test
    main_module.db_pool = None

    # Mock global database configuration constants, making DB_HOST problematic
    # For this test, we expect an error during aiomysql.create_pool if it tries to connect
    # to a non-existent host, or if the constants themselves were None and aiomysql complained.
    # The original code doesn't explicitly raise ValueError for missing env vars INSIDE get_db_pool,
    # it relies on constants being set. If constants are None, aiomysql.create_pool would fail.
    # Let's simulate a failure at the aiomysql.create_pool level for a more direct test of the try-except.
    mocker.patch.object(main_module, 'DATABASE_HOST', 'bad_host_that_will_fail')
    mocker.patch.object(main_module, 'DATABASE_USER', 'user')
    mocker.patch.object(main_module, 'DATABASE_PASSWORD', 'pass')
    mocker.patch.object(main_module, 'DATABASE_NAME', 'db')
    mocker.patch.object(main_module, 'DATABASE_PORT', 1234)

    mock_create_pool = mocker.patch('aiomysql.create_pool', new_callable=AsyncMock)
    mock_create_pool.side_effect = Exception("Connection failed error") # Simulate aiomysql failure

    with pytest.raises(Exception, match="Connection failed error"):
        await main_module.get_db_pool()
    # Ensure db_pool is reset for other tests if it was somehow set
    main_module.db_pool = None

@pytest.mark.asyncio
async def test_get_db_pool_already_initialized(mocker):
    # Simulate db_pool already being initialized
    existing_pool = AsyncMock()
    main_module.db_pool = existing_pool
    mock_create_pool = mocker.patch('aiomysql.create_pool') # To ensure it's not called

    pool = await main_module.get_db_pool()

    assert pool == existing_pool
    mock_create_pool.assert_not_called()
    # Reset db_pool for other tests
    main_module.db_pool = None 
    # Ensure it's reset for subsequent tests that might rely on it being None initially
    mocker.patch.object(main_module, 'db_pool', None)

# Tests for app_lifespan
@pytest.mark.asyncio
async def test_app_lifespan(mocker):
    mock_server = MagicMock() # Mock the FastMCP server instance
    
    # Mock get_db_pool and the pool it returns
    mock_pool_instance = AsyncMock()
    mock_pool_instance.close = MagicMock() # close is sync
    mock_pool_instance.wait_closed = AsyncMock() # wait_closed is async
    
    mock_get_db_pool = mocker.patch('main.get_db_pool', new_callable=AsyncMock)
    mock_get_db_pool.return_value = mock_pool_instance
    
    # Ensure db_pool is None before starting
    main_module.db_pool = None
    
    lifespan_context_manager = main_module.app_lifespan(mock_server)
    
    # Test startup part
    async with lifespan_context_manager as lifespan_ctx:
        mock_get_db_pool.assert_called_once()
        # app_lifespan uses the pool from get_db_pool to create AppContext
        assert lifespan_ctx.db == mock_pool_instance
        # Also, get_db_pool (the original one, if not fully mocked for side effects) sets the global db_pool.
        # To test app_lifespan's effect on the global var through its call to get_db_pool,
        # we'd need get_db_pool mock to also set main_module.db_pool.
        # For simplicity here, we trust get_db_pool is tested elsewhere to set the global.
        # The critical part for app_lifespan is that it USES the pool.
        
    # Test shutdown part (implicitly called by exiting 'async with')
    # The original app_lifespan's finally block would call db_pool.close() etc.
    # Here, db_pool refers to the one obtained from get_db_pool() at startup.
    # We need to ensure that the db_pool that app_lifespan *would* have closed is the one we mocked.
    # Since app_lifespan itself doesn't reassign main_module.db_pool to None on shutdown,
    # we only check that close and wait_closed were called on the pool instance it managed.
    mock_pool_instance.close.assert_called_once()
    mock_pool_instance.wait_closed.assert_called_once()

    # Clean up global db_pool for other tests if it was set by the get_db_pool mock side effect (if any)
    main_module.db_pool = None


# Tests for show_explain_query
@pytest.mark.asyncio
async def test_show_explain_query_success_select(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    # Simulate output from aiomysql.DictCursor for EXPLAIN
    mock_explain_output = [
        {"id": 1, "select_type": "SIMPLE", "table": "coupons", "type": "ref", "possible_keys": "batch_id_index", "key": "batch_id_index", "key_len": "147", "ref": "const", "rows": 1, "Extra": "Using index"}
    ]
    mock_cur.fetchall.return_value = mock_explain_output
    query = "SELECT * FROM coupons WHERE batch_id = 'test'"
    
    result = await main_module.show_explain_query(mock_ctx, query)
    
    mock_cur.execute.assert_called_once_with(f"EXPLAIN {query}")
    assert result == mock_explain_output

@pytest.mark.asyncio
async def test_show_explain_query_non_select(mock_ctx):
    query = "UPDATE coupons SET foo = 'bar'" # Non-SELECT query
    
    result = await main_module.show_explain_query(mock_ctx, query)
    
    assert result == {"error": "You can only perform SELECT queries. Start with SELECT."}

@pytest.mark.asyncio
async def test_show_explain_query_select_empty_result(mock_ctx, mock_db_objects):
    _, _, mock_cur = mock_db_objects
    mock_cur.fetchall.return_value = [] # EXPLAIN returned empty (unusual, but testable)
    query = "SELECT * FROM very_empty_table_or_view"

    result = await main_module.show_explain_query(mock_ctx, query)
    mock_cur.execute.assert_called_once_with(f"EXPLAIN {query}")
    assert result == []

