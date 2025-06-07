import aiomysql
import asyncio

class Database:
    def __init__(self):
        self.pool = None

    async def init(self, host, port, user, password, db_name):
        self.pool = await aiomysql.create_pool(
            host=host,
            port=port,
            user=user,
            password=password,
            db=db_name,
            autocommit=True,
            minsize=1,
            maxsize=10
        )

    async def exec(self, query: str, args: tuple = ()):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)

    async def fetch(self, query: str, args: tuple = ()):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args)
                return await cur.fetchall()

    async def fetchrow(self, query: str, args: tuple = ()):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, args)
                return await cur.fetchone()

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()


db = Database()
