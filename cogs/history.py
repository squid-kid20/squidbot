# SPDX-License-Identifier: AGPL-3.0-only

import discord
import json
import os
import sqlite3
from discord.ext import commands
from main import BotClient
from typing import Any, Optional


class History(commands.Cog):
    def __init__(self, bot: BotClient):
        self.bot = bot
        os.makedirs('databases', exist_ok=True)
        self._connection = sqlite3.connect('databases/history.sqlite', autocommit=False)

        self._connection.execute('PRAGMA foreign_keys = true;')
        self._connection.execute("""
                CREATE TABLE IF NOT EXISTS "messages" (
                    "message_id" INTEGER NOT NULL,
                    "channel_id" INTEGER NOT NULL,
                    "author_id" INTEGER NOT NULL,
                    "version" INTEGER NOT NULL DEFAULT 0,
                    "content" TEXT,
                    "json" TEXT NOT NULL,
                    PRIMARY KEY ("message_id", "version")
                );
            """,
        )
        self._connection.commit()

        self.bot.register_create_message_hook(self._update_message)

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
            self._add_new_message(payload['d'])

    def _add_new_message(self, data: dict[str, Any], version = 0, /) -> None:
        message_id: int = data['id']
        channel_id: int = data['channel_id']
        author_id: int = data['author']['id']
        content: str = data['content']
        raw_json: str = json.dumps(data)

        self._connection.execute("""
                INSERT INTO "messages"
                (message_id, channel_id, author_id, version, content, json)
                VALUES
                (?, ?, ?, ?, ?, ?)
            """,
            (message_id, channel_id, author_id, version, content, raw_json),
        )
        self._connection.commit()

    def _update_message(self, data: dict[str, Any], /) -> None:
        """Add the message to the database by the following logic:
        If the message already exists, check if the content has changed.
        If it hasn't, do nothing.
        If it has, add a new version of the message with the new content.
        If the message doesn't exist, add it as a new message.
        """
        message_id: int = data['id']
        content: str = data['content']

        cursor = self._connection.execute("""
                SELECT MAX("version"), "content"
                FROM "messages"
                WHERE "message_id" = ?
            """,
            (message_id,),
        )

        row: tuple[Optional[int], Optional[str]] = cursor.fetchone()
        version, old_content = row
        if version is None:
            # Message does not exist, add it
            self._add_new_message(data)
            return

        # Message exists, check if content has changed
        if old_content != content:
            self._add_new_message(data, version + 1)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        cursor = self._connection.execute("""
                SELECT MAX("version")
                FROM "messages"
                WHERE "message_id" = ?
            """,
            (payload.message_id,),
        )

        row: tuple[Optional[int]] = cursor.fetchone()
        version, = row

        version = version or 0
        version += 1

        data: dict[str, Any] = payload.data # type: ignore # docs say it's a dict
        self._add_new_message(data, version)

async def setup(bot: BotClient):
    await bot.add_cog(History(bot))
