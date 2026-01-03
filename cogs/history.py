# SPDX-License-Identifier: AGPL-3.0-only

import discord
import json
import os
import pathlib
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
                    "content" TEXT NOT NULL,
                    "attachments" TEXT NOT NULL,
                    "json" TEXT NOT NULL,
                    PRIMARY KEY ("message_id", "version")
                );
            """,
        )
        self._connection.execute("""
                CREATE TABLE IF NOT EXISTS "channels" (
                    "channel_id" INTEGER PRIMARY KEY NOT NULL,
                    "last_message_id" INTEGER
                );
            """)
        self._connection.commit()

        self.bot.register_create_message_hook(self._update_message)

    async def _get_new_messages(self, channel: discord.TextChannel, /) -> None:
        cursor = self._connection.execute("""
                SELECT "channel_id", "last_message_id"
                FROM "channels"
                WHERE "channel_id" = ?
            """,
            (channel.id,),
        )
        row: tuple[Optional[int], Optional[int]] | None = cursor.fetchone()
        db_channel_id, last_message_id = row or (None, None)

        if db_channel_id is None:
            self._connection.execute("""
                    INSERT INTO "channels" ("channel_id", "last_message_id")
                    VALUES (?, ?)
                """,
                (channel.id, last_message_id),
            )
            self._connection.commit()

        last_message_id = last_message_id or 0
        async for message in channel.history(after=discord.Object(id=last_message_id), limit=None, oldest_first=True):
            # all fetched messages trigger _update_message hook

            last_message_id = message.id
            self._connection.execute("""
                    UPDATE "channels"
                    SET "last_message_id" = ?
                    WHERE "channel_id" = ?
                """,
                (last_message_id, channel.id),
            )
            self._connection.commit()

            if message.attachments:
                await self._download_attachments(message)

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
        attachments: str = json.dumps(data['attachments'])
        raw_json: str = json.dumps(data)

        self._connection.execute("""
                INSERT INTO "messages"
                (message_id, channel_id, author_id, version, content, attachments, json)
                VALUES
                (?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, channel_id, author_id, version, content, attachments, raw_json),
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
                SELECT MAX("version"), "content", "attachments"
                FROM "messages"
                WHERE "message_id" = ?
            """,
            (message_id,),
        )

        row: tuple[Optional[int], Optional[str], Optional[str]] | None = cursor.fetchone()
        version, old_content, old_attachments = row or (None, None, None)
        if version is None or old_content is None or old_attachments is None:
            # Message does not exist, add it
            self._add_new_message(data)
            return

        # Message exists, check if anything has changed
        if old_content != content or json.loads(old_attachments) != data['attachments']:
            self._add_new_message(data, version + 1)

    def get_message(self, message_id: int, /) -> dict[str, Any] | None:
        """Get the latest version of a message by its ID, if it exists."""

        cursor = self._connection.execute("""
                SELECT MAX("version"), "json"
                FROM "messages"
                WHERE "message_id" = ?
            """,
            (message_id,),
        )

        row: tuple[Optional[int], Optional[str]] | None= cursor.fetchone()
        version, raw_json = row or (None, None)
        if version is None or raw_json is None:
            return None

        data: dict[str, Any] = json.loads(raw_json)
        return data

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.attachments:
            await self._download_attachments(message)

    async def _download_attachments(self, message: discord.Message, /) -> None:
        if message.guild is None:
            return

        downloaded_ids = self._get_downloaded_attachment_ids(message.guild.id, message.channel.id, message.id)
        path = f'media/{message.guild.id}/{message.channel.id}/{message.id}/'
        os.makedirs(path, exist_ok=True)

        for attachment in message.attachments:
            if attachment.id in downloaded_ids:
                continue

            filename = f'a{attachment.id}-{attachment.filename}'
            filepath = pathlib.Path(path, filename)

            await attachment.save(filepath)

    def _get_downloaded_attachment_ids(self, guild_id: int, channel_id: int, message_id: int, /) -> list[int]:
        path = f'media/{guild_id}/{channel_id}/{message_id}/'
        if not os.path.exists(path):
            return []

        ids: list[int] = []

        for filename in os.listdir(path):
            if filename.startswith('a'):
                filename = filename[1:]
                filename = filename.split('-', 1)[0]
                attachment_id = int(filename)
                ids.append(attachment_id)

        return ids

    def get_downloaded_attachments(
        self, guild_id: int, channel_id: int, message_id: int, /,
        *, attachment_ids: list[int] | None = None,
        exclude_ids: list[int] | None = None,
        descriptions: dict[int, str] | None = None,
    ) -> list[discord.File]:
        """Get the downloaded attachments for a message.
        If attachment_ids is specified, only attachments returned are those with IDs in attachment_ids.
        If exclude_ids is specified, attachments with IDs in exclude_ids are not returned.
        If an ID has a description in descriptions, the corresponding File will also have that description.
        """

        path = f'media/{guild_id}/{channel_id}/{message_id}/'
        if not os.path.exists(path):
            return []

        files: list[discord.File] = []
        descriptions = descriptions or {}

        for filename in os.listdir(path):
            if filename.startswith('a'):
                attachment_id = int(filename[1:].split('-', 1)[0])
                if attachment_ids is not None and attachment_id not in attachment_ids:
                    continue
                if exclude_ids is not None and attachment_id in exclude_ids:
                    continue

                filepath = pathlib.Path(path, filename)
                filename = filename.split('-', 1)[1]
                files.append(discord.File(filepath, filename, description=descriptions.get(attachment_id)))

        return files

    def get_and_update_message(self, payload: discord.RawMessageUpdateEvent) -> dict[str, Any] | None:
        """Get the latest version of a message by its ID, if it exists.
        Also, add a new version of the message with the updated data.
        Returns the latest version of the message before the update.
        """

        cursor = self._connection.execute("""
                SELECT MAX("version"), "json"
                FROM "messages"
                WHERE "message_id" = ?
            """,
            (payload.message_id,),
        )

        row: tuple[Optional[int], Optional[str]] | None = cursor.fetchone()
        version, old_json = row or (None, None)

        version = version or 0
        version += 1

        data: dict[str, Any] = payload.data # type: ignore # docs say it's a dict
        if old_json is not None:
            new_data: dict[str, Any] = json.loads(old_json)
            new_data.update(data)
        else:
            new_data = data
        self._add_new_message(new_data, version)

        if version is None or old_json is None:
            return None

        old_data: dict[str, Any] = json.loads(old_json)
        return old_data

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        await self._download_attachments(payload.message)

async def setup(bot: BotClient):
    await bot.add_cog(History(bot))
