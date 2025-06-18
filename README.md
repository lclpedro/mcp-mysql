# MCPs
## MySQL Managing MCP

How to use this MCP:
1. Import imagem in the docker-compose with how to docker-compose.yml
```yaml
version: '3.8'

services:
  mcp-mysql:
    image: lclpedro/mcp-mysql:latest
    container_name: mcp-mysql
    ports:
      - "3002:3002"
    environment:
      - MYSQL_DATABASE_HOST=mysql-db
      - MYSQL_DATABASE_PORT=3306
      - MYSQL_DATABASE_USER=test
      - MYSQL_DATABASE_PASSWORD=root
      - MYSQL_DATABASE_NAME=testdb
    depends_on:
      - testdb
    volumes:
      - poetry-cache:/root/.cache/pypoetry

  your-database-mysql:
    image: mysql:8.0
    environment:
      - MYSQL_DATABASE=couponsdbx
      - MYSQL_USER=test
      - MYSQL_PASSWORD=root
      - MYSQL_ROOT_PASSWORD=root
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

volumes:
  your-database-mysql:
```
2. Run docker-compose up -d
3. Configure MCP Server in this IDE:
```json
{
    "mcpServers": {
        "mysqlManaging":{
            "serverUrl": "http://localhost:3002/sse"
        }
    }
}
```
4. Load MCPs in IDE.

### Others Executions

If your running only MCP server, you can run it with:
```bash
> git clone https://github.com/lclpedro/mcp-mysql.git
> cd mcp-mysql
> cp .env.example .env
> poetry install
> poetry run python main.py
```

### Tools available:
- health_check
- list_tables
- get_table_schema
- execute_query
- show_indexes_table
- show_explain_query

### Contributing with this MCP

1. Fork it
2. Create your feature branch (git checkout -b feature/AmazingFeature)
3. Commit your changes (git commit -m 'Add some AmazingFeature')
4. Push to the branch (git push origin feature/AmazingFeature)
5. Open a Pull Request
