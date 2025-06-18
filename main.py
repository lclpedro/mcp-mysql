from collections.abc import AsyncIterator
from dataclasses import dataclass
import logging
import aiomysql
from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager
from typing import Union


# Load environment variables defined in your docker-compose.yaml
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_HOST = os.getenv("MYSQL_DATABASE_HOST")
DATABASE_PORT = int(os.getenv("MYSQL_DATABASE_PORT", "3306"))
DATABASE_USER = os.getenv("MYSQL_DATABASE_USER")
DATABASE_PASSWORD = os.getenv("MYSQL_DATABASE_PASSWORD")
DATABASE_NAME = os.getenv("MYSQL_DATABASE_NAME")

# Application context
@dataclass
class AppContext:
    db: aiomysql.Pool

# Database pool
db_pool = None

async def get_db_pool() -> aiomysql.Pool:
    global db_pool
    if db_pool is None:
        try:
            logger.info(f"Connecting to MySQL database at {DATABASE_HOST}:{DATABASE_PORT}")
            db_pool = await aiomysql.create_pool(
                host=DATABASE_HOST,
                port=DATABASE_PORT,
                user=DATABASE_USER,
                password=DATABASE_PASSWORD,
                db=DATABASE_NAME,
                autocommit=False,
            )
            logger.info("Database connection established successfully")
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            raise
    return db_pool

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    logger.info("Initializing MCP lifecycle...")
    db = await get_db_pool()
    logger.info("Database pool ready, MCP server initialized and ready to receive requests.")
    try:
        yield AppContext(db=db)
    finally:
        logger.info("Shutting down MCP server and database pool...")
        if db: # 'db' is the pool instance obtained from get_db_pool at startup
            db.close()
            await db.wait_closed()
        logger.info("Database pool closed.")

# Initialize the MCP server
mcp = FastMCP(
    "MySQLMCP", 
    lifespan=app_lifespan,
    host="0.0.0.0", 
    port=3002, 
)

@mcp.tool()
async def health_check(ctx: Context) -> dict:
    """
    Check the health of the database connection.

    Returns:
        A dictionary with the status of the database connection.
    """
    db = ctx.request_context.lifespan_context.db
    try:
        async with db.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                test = await cur.fetchone()
        return {"status": "healthy", "database": "connected", "result": test[0]}
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"status": "error", "error": "Service unavailable"}

@mcp.tool()
async def list_tables(ctx: Context) -> list[dict]:
    """
    List all tables in the database.

    Returns:
        A list of tables with the table names.
    """
    db = ctx.request_context.lifespan_context.db
    async with db.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SHOW TABLES")
            result = await cur.fetchall()
    return [{"tablename": row[0]} for row in result]

@mcp.tool()
async def get_table_schema(ctx: Context, table_name: str) -> list[dict]:
    """
    Get the schema of a table.

    Args:
        table_name: The name of the table to get the schema for.

    Returns:
        A list of dictionaries with the column names and data types.
    """
    db = ctx.request_context.lifespan_context.db
    async with db.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(f"DESCRIBE {table_name}")
            result = await cur.fetchall()
            return [{"column_name": row["Field"], "data_type": row["Type"]} for row in result]

@mcp.tool()
async def get_table_data(ctx: Context, query: str) -> Union[dict, list[dict]]:
    """
    Get the data from a table.

    Args:
        query: The SQL query to execute.

    Returns:
        A dictionary or list of dictionaries with the query results.
    """
    db = ctx.request_context.lifespan_context.db
    async with db.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            logger.info(f"Executing query: {query}")
            await cur.execute(query)
            result = await cur.fetchall()
            return result

@mcp.tool()
async def show_indexes_table(ctx: Context, table_name: str) -> list[dict]:
    """
    Show the indexes of a table.

    Args:
        table_name: The name of the table to show the indexes for.

    Returns:
        A list of dictionaries with the index names and column names.
    """
    db = ctx.request_context.lifespan_context.db
    async with db.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(f"SHOW INDEX FROM {table_name}")
            result = await cur.fetchall()
            indexes_map = {}
            for row in result:
                index_name = row["Key_name"]
                column_name = row["Column_name"]
                # Seq_in_index is 1-based index of column in index
                seq_in_index = row["Seq_in_index"]

                if index_name not in indexes_map:
                    indexes_map[index_name] = []
                indexes_map[index_name].append((seq_in_index, column_name))
            
            output_list = []
            for index_name, cols_with_seq in indexes_map.items():
                # Sort columns by sequence number (the first element of the tuple)
                cols_with_seq.sort(key=lambda x: x[0])
                # Extract just the column names in the correct order
                sorted_columns = [col_name for seq, col_name in cols_with_seq]
                output_list.append({"index_name": index_name, "columns": sorted_columns})
            return output_list

@mcp.tool()
async def show_explain_query(ctx: Context, query: str) -> Union[dict, list[dict]]:
    """
    Show the explain of a query.

    Args:
        query: The SQL query to explain.

    Returns:
        A dictionary or list of dictionaries with the explain results.
    """
    db = ctx.request_context.lifespan_context.db
    async with db.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(f"EXPLAIN {query}")
            result = await cur.fetchall()
            return [dict(row) for row in result]

if __name__ == "__main__":
    logger.info("Starting MCP server...")
    mcp.run(
        transport='sse'
    )
