# SPDX-License-Identifier: AGPL-3.0-only

import datetime
import discord
import interface
import json
import os
import pathlib
from discord.ext import commands
from .history import History
from typing import Any


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.configs: dict[str, dict[str, dict[str, bool]]] = {}
        self.load_log_configs()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not isinstance(message.channel, discord.abc.GuildChannel):
            return
        if message.guild is None:
            return
        if str(message.guild.id) not in self.configs:
            return

        guild_config = self.configs[str(message.guild.id)]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('message_delete', False):
                continue
            log_channel = self.bot.get_channel(int(log_channel_id))
            if not isinstance(log_channel, discord.TextChannel):
                continue
            if log_channel.guild != message.guild:
                continue

            embed = discord.Embed(
                colour=get_colour(message.author),
                description=message.content,
            ).set_author(
                name=message.author.display_name,
                icon_url=message.author.display_avatar.url,
            ).set_footer(
                text=id_tags(
                    user_id=message.author.id,
                    message_id=message.id,
                    channel_id=message.channel.id,
                ),
            )
            reltime = relative_time(message.created_at)

            await log_channel.send(
                f'**\N{WASTEBASKET} MESSAGE DELETED**\n'
                f'Sent {reltime} by {message.author.mention} in {message.channel.mention}',
                embed=embed,
            )

            if message.attachments:
                ids = [attachment.id for attachment in message.attachments]
                history: History = self.bot.get_cog('History') # type: ignore
                assert(history)

                descriptions = {attachment.id: attachment.description for attachment in message.attachments if attachment.description}

                files = history.get_downloaded_attachments(
                    message.guild.id, message.channel.id, message.id,
                    attachment_ids=ids,
                    descriptions=descriptions,
                )

                if files:
                    await log_channel.send(
                        f'\N{PAPERCLIP} _Attachments of message {message.id}:_',
                        files=files,
                    )
                else:
                    await log_channel.send(
                        f'\N{PAPERCLIP} _Attachments of message {message.id} could not be found._',
                    )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.cached_message is not None:
            return

        message_channel = self.bot.get_channel(payload.channel_id)
        if not isinstance(message_channel, discord.abc.GuildChannel):
            return
        if payload.guild_id is None:
            return
        if str(payload.guild_id) not in self.configs:
            return

        guild_config = self.configs[str(payload.guild_id)]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('message_delete', False):
                continue
            log_channel = self.bot.get_channel(int(log_channel_id))
            if not isinstance(log_channel, discord.TextChannel):
                continue
            if log_channel.guild.id != payload.guild_id:
                continue

            history: History = self.bot.get_cog('History') # type: ignore
            assert(history)

            data = history.get_message(payload.message_id)
            if data is None:
                await self._log_uncached_message_delete(log_channel, payload)
            else:
                await self._log_historical_message_delete(log_channel, payload, data)

    async def _log_uncached_message_delete(self, log_channel: discord.TextChannel, payload: discord.RawMessageDeleteEvent, /) -> None:
        embed = discord.Embed(
            colour=discord.Colour.red(),
            title='Uncached message',
            description='_Content unknown_',
        ).set_footer(
            text=id_tags(
                message_id=payload.message_id,
                channel_id=payload.channel_id,
            ),
        )

        await log_channel.send(
            f'**\N{WASTEBASKET} MESSAGE DELETED**\n'
            f'In <#{payload.channel_id}>',
            embed=embed,
        )

        # I don't think it's possible that we have the attachments of a message even though it's uncached, but just in case
        history: History = self.bot.get_cog('History') # type: ignore
        assert(history)
        files = history.get_downloaded_attachments(payload.guild_id or 0, payload.channel_id, payload.message_id)
        if files:
            await log_channel.send(
                f'\N{PAPERCLIP} _Attachments of message {payload.message_id}:_',
                files=files,
            )

    async def _log_historical_message_delete(self, log_channel: discord.TextChannel, payload: discord.RawMessageDeleteEvent, data: dict[str, Any], /) -> None:
        author_id: int = int(data['author']['id'])
        content: str = data['content']
        timestamp: str = data['timestamp']
        attachments: list[dict[str, Any]] = data['attachments']
        try:
            author = (log_channel.guild.get_member(author_id)
                or self.bot.get_user(author_id)
                or await self.bot.fetch_user(author_id))
        except (discord.NotFound, discord.HTTPException):
            author = None

        embed = discord.Embed(
            colour=get_colour(author) if author else None,
            description=content,
        )

        if author:
            embed.set_author(
                name=author.display_name,
                icon_url=author.display_avatar.url,
            )
        else:
            embed.set_author(
                name=f'User {author_id}',
            )

        embed.set_footer(
            text=id_tags(
                user_id=author_id,
                message_id=payload.message_id,
                channel_id=payload.channel_id,
            ),
        )
        reltime = relative_time(discord.utils.parse_time(timestamp))

        await log_channel.send(
            f'**\N{WASTEBASKET} MESSAGE DELETED**\n'
            f'Sent {reltime} by <@{author_id}> in <#{payload.channel_id}>',
            embed=embed,
        )

        if attachments:
            ids: list[int] = [int(attachment['id']) for attachment in attachments]
            history: History = self.bot.get_cog('History') # type: ignore
            assert(history)

            descriptions: dict[int, str] = {int(attachment['id']): attachment['description'] for attachment in attachments if 'description' in attachment}

            files = history.get_downloaded_attachments(
                payload.guild_id or 0, payload.channel_id, payload.message_id,
                attachment_ids=ids,
                descriptions=descriptions,
            )

            if files:
                await log_channel.send(
                    f'\N{PAPERCLIP} _Attachments of message {payload.message_id}:_',
                    files=files,
                )
            else:
                await log_channel.send(
                    f'\N{PAPERCLIP} _Attachments of message {payload.message_id} could not be found._',
                )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not isinstance(before.channel, discord.abc.GuildChannel):
            return
        if before.guild is None:
            return
        if str(before.guild.id) not in self.configs:
            return

        guild_config = self.configs[str(before.guild.id)]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('message_edit', False):
                continue
            log_channel = self.bot.get_channel(int(log_channel_id))
            if not isinstance(log_channel, discord.TextChannel):
                continue
            if log_channel.guild != before.guild:
                continue

            if before.content != after.content:
                # FIXME: handle 4000 character limit
                embed = discord.Embed(
                    colour=get_colour(before.author),
                ).add_field(
                    name='Before (empty)' if not before.content else 'Before',
                    value=before.content or '_No content_',
                    inline=False,
                ).add_field(
                    name='After (empty)' if not after.content else 'After',
                    value=after.content or '_No content_',
                    inline=False,
                ).set_author(
                    name=before.author.display_name,
                    icon_url=before.author.display_avatar.url,
                ).set_footer(
                    text=id_tags(
                        user_id=before.author.id,
                        message_id=before.id,
                        channel_id=before.channel.id,
                    ),
                )

                reltime = relative_time(before.created_at)
                await log_channel.send(
                    f'**\N{MEMO} MESSAGE EDITED**\n'
                    f'Sent {reltime} by {before.author.mention} at {before.jump_url}',
                    embed=embed,
                )

            removed_attachment_ids = [attachment.id for attachment in before.attachments if attachment not in after.attachments]
            if removed_attachment_ids:
                history: History = self.bot.get_cog('History') # type: ignore
                assert(history)

                descriptions = {attachment.id: attachment.description for attachment in before.attachments if attachment.description}

                files = history.get_downloaded_attachments(
                    before.guild.id, before.channel.id, before.id,
                    attachment_ids=removed_attachment_ids,
                    descriptions=descriptions,
                )

                embed = discord.Embed(
                    description=before.content,
                    colour=get_colour(before.author),
                ).set_author(
                    name=before.author.display_name,
                    icon_url=before.author.display_avatar.url,
                ).set_footer(
                    text=id_tags(
                        user_id=before.author.id,
                        message_id=before.id,
                        channel_id=before.channel.id,
                    ),
                )

                reltime = relative_time(before.created_at)
                text = [
                    '**\N{MEMO} MESSAGE ATTACHMENTS REMOVED**',
                    f'Sent {reltime} by {before.author.mention} at {before.jump_url}',
                ]
                if files:
                    text.append(f'\N{PAPERCLIP} _Removed attachments are attached._')
                    await log_channel.send('\n'.join(text), embed=embed, files=files)
                else:
                    text.append(f'\N{PAPERCLIP} _Removed attachments could not be found._')
                    await log_channel.send('\n'.join(text), embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if str(member.guild.id) not in self.configs:
            return

        guild_config = self.configs[str(member.guild.id)]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('member_join', False):
                continue
            log_channel = self.bot.get_channel(int(log_channel_id))
            if not isinstance(log_channel, discord.TextChannel):
                continue
            if log_channel.guild != member.guild:
                continue

            embed = discord.Embed(
                colour=id_colour(member.id),
            ).set_author(
                name=member.display_name,
                icon_url=member.display_avatar.url,
            ).set_thumbnail(
                url=member.display_avatar.url,
            ).add_field(
                name='Account created',
                value=relative_time(member.created_at),
            ).add_field(
                name='Server now has',
                value=f'{member.guild.member_count} members',
            ).set_footer(
                text=id_tags(user_id=member.id),
            )

            if member.bot:
                header = '\N{ROBOT FACE} BOT ADDED TO SERVER'
            else:
                header = '\N{WAVING HAND SIGN} MEMBER JOINED'

            await log_channel.send(
                f'**{header}**\n'
                f'{member.mention}',
                embed=embed,
            )

    def load_log_configs(self):
        """Load log configurations for each channel."""
        for filename in os.listdir('logs/'):
            if filename.endswith('.json'):
                guild_id = filename[:-5]
                with open(f'logs/{filename}', 'r') as file:
                    config = json.load(file)
                self.configs[guild_id] = config


def id_tags(
    *,
    user_id: int | None = None,
    message_id: int | None = None,
    channel_id: int | None = None,
) -> str:
    ids = []
    if user_id is not None:
        ids.append(f'\N{BUST IN SILHOUETTE}{user_id}')
    if message_id is not None:
        ids.append(f'\N{SPEECH BALLOON}{message_id}')
    if channel_id is not None:
        ids.append(f'\N{TELEVISION}{channel_id}')
    return ' '.join(ids)

def get_colour(user: discord.User | discord.Member, /) -> discord.Colour | None:
    if user.colour == discord.Colour.default():
        return None
    return user.colour

def relative_time(dt: datetime.datetime, /) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds == 0:
        return 'now'

    if seconds < 0:
        # This can happen and it's likely due to one or both clocks being wrong.
        # Precision doesn't matter so avoid returning a "-1s ago" or similar.
        return 'now'

    if seconds < 60:
        duration = f'{seconds}s'
    elif seconds < 60 * 60:
        minutes = seconds // 60
        seconds = seconds % 60
        duration = f'{minutes}m{seconds}s'
    elif seconds < 60 * 60 * 24:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        duration = f'{hours}h{minutes}m'
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        duration = f'{days}d{hours}h'

    return f'{duration} ago'

def id_colour(object_id: int, /) -> discord.Colour:
    """Generate a colour from an ID."""
    unix_time = int(discord.utils.snowflake_time(object_id).timestamp())
    r = (unix_time >> 16) & 0xFF
    g = (unix_time >> 8) & 0xFF
    b = unix_time & 0xFF
    return discord.Colour.from_rgb(r, g, b)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
