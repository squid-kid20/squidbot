# SPDX-License-Identifier: AGPL-3.0-only

import json
import os
import sqlite3
from discord.ext import commands
from typing import Any


class History(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        os.makedirs('databases', exist_ok=True)
        self.connection = sqlite3.connect('databases/history.sqlite', autocommit=False)

        self.connection.execute('PRAGMA foreign_keys = true;')
        self.connection.execute("""
                CREATE TABLE IF NOT EXISTS 'messages' (
                    'message_id' INTEGER PRIMARY KEY NOT NULL,
                    'channel_id' INTEGER NOT NULL,
                    'author_id' INTEGER NOT NULL,
                    'content' TEXT,
                    'json' TEXT
                );
            """,
        )
        self.connection.commit()

    @commands.Cog.listener()
    async def on_socket_raw_receive(self, msg: str):
        """Discord sends message data we don't necessarily want to parse.
        They also may add more data that existing libraries don't handle.
        For future-proofing, we store the raw JSON of all messages.

        This is the only way to get the raw JSON of a message event in discord.py
        (the library doesn't have on_raw_message).
        """

        payload: dict[str, Any] = json.loads(msg)
        if payload['t'] == 'MESSAGE_CREATE':
            data: dict[str, Any] = payload['d']

            message_id: int = data['id']
            channel_id: int = data['channel_id']
            author_id: int = data['author']['id']
            content: str = data['content']
            raw_json: str = json.dumps(data)

            self.connection.execute("""
                    INSERT INTO 'messages'
                    (message_id, channel_id, author_id, content, json)
                    VALUES
                    (?, ?, ?, ?, ?)
                """,
                (message_id, channel_id, author_id, content, raw_json),
            )
            self.connection.commit()


async def setup(bot: commands.Bot):
    await bot.add_cog(History(bot))
