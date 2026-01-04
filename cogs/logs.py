# SPDX-License-Identifier: AGPL-3.0-only

import datetime
import discord
import interface
import json
import os
from discord.ext import commands
from .history import History
from typing import Any, Optional


VALID_LOG_ITEMS = (
    'message_delete',
    'message_edit',
    'member_join',
)

class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.configs: dict[int, dict[int, dict[str, bool]]] = {}
        self.load_log_configs()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not isinstance(message.channel, discord.abc.GuildChannel):
            return
        if message.guild is None:
            return
        if message.guild.id not in self.configs:
            return

        guild_config = self.configs[message.guild.id]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('message_delete', False):
                continue
            log_channel = self.bot.get_channel(log_channel_id)
            if not isinstance(log_channel, discord.TextChannel):
                continue
            if log_channel.guild != message.guild:
                continue

            await self._log_cached_message_delete(log_channel, message)

    async def _log_cached_message_delete(self, log_channel: discord.TextChannel, message: discord.Message, /) -> None:
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
            '**\N{WASTEBASKET} MESSAGE DELETED**\n'
            f'Sent {reltime} by {message.author.mention} in <#{message.channel.id}>',
            embed=embed,
        )

        if message.attachments:
            ids = [attachment.id for attachment in message.attachments]
            assert(message.guild)
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
        if payload.guild_id not in self.configs:
            return

        guild_config = self.configs[payload.guild_id]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('message_delete', False):
                continue
            log_channel = self.bot.get_channel(log_channel_id)
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
            '**\N{WASTEBASKET} MESSAGE DELETED**\n'
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
            '**\N{WASTEBASKET} MESSAGE DELETED**\n'
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
        if before.guild.id not in self.configs:
            return

        guild_config = self.configs[before.guild.id]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('message_edit', False):
                continue
            log_channel = self.bot.get_channel(log_channel_id)
            if not isinstance(log_channel, discord.TextChannel):
                continue
            if log_channel.guild != before.guild:
                continue

            await self._dispatch_message_edit(log_channel, before, after)

    async def _dispatch_message_edit(self, log_channel: discord.TextChannel, before: discord.Message, after: discord.Message, /) -> None:
        if before.content != after.content:
            await self._log_cached_message_edit(log_channel, before, after)

        removed_attachment_ids = [attachment.id for attachment in before.attachments if attachment not in after.attachments]
        if removed_attachment_ids:
            await self._log_cached_removed_attachments(log_channel, before, removed_attachment_ids)

    async def _log_cached_message_edit(self, log_channel: discord.TextChannel, before: discord.Message, after: discord.Message, /) -> None:
        embed = discord.Embed(
            colour=get_colour(before.author),
        )

        if len(before.content) <= 1024 and len(after.content) <= 1024:
            embed.add_field(
                name='Before (empty)' if not before.content else 'Before',
                value=before.content or '_No content_',
                inline=False,
            ).add_field(
                name='After (empty)' if not after.content else 'After',
                value=after.content or '_No content_',
                inline=False,
            )
        else:
            embed.title = 'Before (empty)' if not before.content else 'Before'
            embed.description = before.content

        embed.set_author(
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
            '**\N{MEMO} MESSAGE EDITED**\n'
            f'Sent {reltime} by {before.author.mention} at {before.jump_url}',
            embed=embed,
        )

    async def _log_cached_removed_attachments(self, log_channel: discord.TextChannel, before: discord.Message, removed_attachment_ids: list[int], /) -> None:
        assert(before.guild)
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
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        # We have to handle this rather than the history cog in order to avoid
        # a race condition where the history cog could update the message before
        # we grab the latest (older) version.
        history: History = self.bot.get_cog('History') # type: ignore
        assert(history)
        data = history.get_and_update_message(payload)

        if payload.cached_message is not None:
            return

        message_channel = self.bot.get_channel(payload.channel_id)
        if not isinstance(message_channel, discord.abc.GuildChannel):
            return
        if payload.guild_id is None:
            return
        if payload.guild_id not in self.configs:
            return

        guild_config = self.configs[payload.guild_id]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('message_edit', False):
                continue
            log_channel = self.bot.get_channel(log_channel_id)
            if not isinstance(log_channel, discord.TextChannel):
                continue
            if log_channel.guild.id != payload.guild_id:
                continue

            if data is None:
                await self._log_uncached_message_edit(log_channel, payload)
            else:
                await self._dispatch_historical_message_edit(log_channel, payload, data)

    async def _log_uncached_message_edit(self, log_channel: discord.TextChannel, payload: discord.RawMessageUpdateEvent, /) -> None:
        embed = discord.Embed(
            title='Uncached message',
            colour=get_colour(payload.message.author),
            description=payload.message.content,
        ).set_author(
            name=payload.message.author.display_name,
            icon_url=payload.message.author.display_avatar.url,
        ).set_footer(
            text=id_tags(
                user_id=payload.message.author.id,
                message_id=payload.message.id,
                channel_id=payload.message.channel.id,
            ),
        )

        reltime = relative_time(payload.message.created_at)
        await log_channel.send(
            '**\N{MEMO} MESSAGE EDITED**\n'
            f'Sent {reltime} by {payload.message.author.mention} at {payload.message.jump_url}',
            embed=embed,
        )

        # I don't think it's possible that we have the attachments of a message even though it's uncached, but just in case
        exclude_ids = [attachment.id for attachment in payload.message.attachments]
        history: History = self.bot.get_cog('History') # type: ignore
        assert(history)
        files = history.get_downloaded_attachments(payload.guild_id or 0, payload.channel_id, payload.message_id, exclude_ids=exclude_ids)
        if files:
            await log_channel.send(
                f'\N{PAPERCLIP} _Previous attachments of message {payload.message_id}:_',
                files=files,
            )

    async def _dispatch_historical_message_edit(self, log_channel: discord.TextChannel, payload: discord.RawMessageUpdateEvent, data: dict[str, Any], /) -> None:
        before_content: str = data['content']

        if before_content != payload.message.content:
            await self._log_historical_message_edit(log_channel, payload, before_content)

        before_attachments: list[dict[str, Any]] = data['attachments']
        removed_attachment_ids = [int(attachment['id']) for attachment in before_attachments if attachment not in payload.message.attachments]
        if removed_attachment_ids:
            await self._log_historical_removed_attachments(log_channel, payload, before_content, before_attachments, removed_attachment_ids)

    async def _log_historical_message_edit(self, log_channel: discord.TextChannel, payload: discord.RawMessageUpdateEvent, before_content: str, /) -> None:
        embed = discord.Embed(
            colour=get_colour(payload.message.author),
        )

        if len(before_content) <= 1024 and len(payload.message.content) <= 1024:
            embed.add_field(
                name='Before (empty)' if not before_content else 'Before',
                value=before_content or '_No content_',
                inline=False,
            ).add_field(
                name='After (empty)' if not payload.message.content else 'After',
                value=payload.message.content or '_No content_',
                inline=False,
            )
        else:
            embed.title = 'Before (empty)' if not before_content else 'Before'
            embed.description = before_content

        embed.set_author(
            name=payload.message.author.display_name,
            icon_url=payload.message.author.display_avatar.url,
        ).set_footer(
            text=id_tags(
                user_id=payload.message.author.id,
                message_id=payload.message.id,
                channel_id=payload.message.channel.id,
            ),
        )

        reltime = relative_time(payload.message.created_at)
        await log_channel.send(
            '**\N{MEMO} MESSAGE EDITED**\n'
            f'Sent {reltime} by {payload.message.author.mention} at {payload.message.jump_url}',
            embed=embed,
        )

    async def _log_historical_removed_attachments(self, log_channel: discord.TextChannel, payload: discord.RawMessageUpdateEvent, before_content: str, before_attachments: list[dict[str, Any]], removed_attachment_ids: list[int], /) -> None:
        history: History = self.bot.get_cog('History') # type: ignore
        assert(history)

        descriptions: dict[int, str] = {int(attachment['id']): attachment['description'] for attachment in before_attachments if 'description' in attachment}

        files = history.get_downloaded_attachments(
            payload.guild_id or 0, payload.channel_id, payload.message_id,
            attachment_ids=removed_attachment_ids,
            descriptions=descriptions,
        )

        embed = discord.Embed(
            description=before_content,
            colour=get_colour(payload.message.author),
        ).set_author(
            name=payload.message.author.display_name,
            icon_url=payload.message.author.display_avatar.url,
        ).set_footer(
            text=id_tags(
                user_id=payload.message.author.id,
                message_id=payload.message.id,
                channel_id=payload.message.channel.id,
            ),
        )

        reltime = relative_time(payload.message.created_at)
        text = [
            '**\N{MEMO} MESSAGE ATTACHMENTS REMOVED**',
            f'Sent {reltime} by {payload.message.author.mention} at {payload.message.jump_url}',
        ]
        if files:
            text.append(f'\N{PAPERCLIP} _Removed attachments are attached._')
            await log_channel.send('\n'.join(text), embed=embed, files=files)
        else:
            text.append(f'\N{PAPERCLIP} _Removed attachments could not be found._')
            await log_channel.send('\n'.join(text), embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id not in self.configs:
            return

        guild_config = self.configs[member.guild.id]

        for log_channel_id, log_channel_config in guild_config.items():
            if not log_channel_config.get('member_join', False):
                continue
            log_channel = self.bot.get_channel(log_channel_id)
            if not isinstance(log_channel, discord.TextChannel):
                continue
            if log_channel.guild != member.guild:
                continue

            await self._log_member_join(log_channel, member)

    async def _log_member_join(self, log_channel: discord.TextChannel, member: discord.Member, /):
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
        """Load log configurations for each guild."""
        for filename in os.listdir('logs/'):
            if filename.endswith('.json'):
                with open(f'logs/{filename}', 'r') as file:
                    json_data: dict[str, dict[str, bool]] = json.load(file)

                config = {int(key): value for key, value in json_data.items()}

                guild_id = int(filename[:-5])
                self.configs[guild_id] = config

    def save_log_config(self, guild_id: int, /):
        """Save log configurations for a guild."""
        config = self.configs[guild_id]
        json_data = {str(key): value for key, value in config.items()}

        with open(f'logs/{guild_id}.json', 'w') as file:
            json.dump(json_data, file, indent=4)

    @commands.guild_only()
    #@commands.hybrid_group()
    @commands.group()
    async def log(self, ctx: commands.Context[commands.Bot]) -> None:
        #await interface.reply(ctx, 'argument required')
        pass

    async def _cmd_check_permission(self, ctx: commands.Context[commands.Bot], channel: discord.TextChannel) -> bool:
        assert(isinstance(ctx.author, discord.Member))
        permissions = channel.permissions_for(ctx.author)
        if not permissions.manage_channels:
            await interface.reply(ctx, f"You don't have permission to manage {channel.mention}.")
            return False
        return True

    @log.command()
    async def create(self, ctx: commands.Context[commands.Bot], channel: discord.TextChannel) -> None:
        if not await self._cmd_check_permission(ctx, channel):
            return

        assert(ctx.guild)
        if ctx.guild.id not in self.configs:
            self.configs[ctx.guild.id] = {}

        if channel.id in self.configs[ctx.guild.id]:
            await interface.reply(ctx, f'{channel.mention} is already a log channel.')
            return

        self.configs[ctx.guild.id][channel.id] = {}
        self.save_log_config(ctx.guild.id)

        await interface.reply(ctx, f"Created log channel {channel.mention}. Note that it won't log anything yet until log items are enabled.")

    @log.command()
    async def delete(self, ctx: commands.Context[commands.Bot], channel: discord.TextChannel) -> None:
        if not await self._cmd_check_permission(ctx, channel):
            return

        assert(ctx.guild)
        if ctx.guild.id not in self.configs:
            await interface.reply(ctx, 'There are no log channels in this server.')
            return

        if channel.id not in self.configs[ctx.guild.id]:
            await interface.reply(ctx, f'{channel.mention} is already not a log channel.')
            return

        del self.configs[ctx.guild.id][channel.id]
        if not self.configs[ctx.guild.id]:
            del self.configs[ctx.guild.id]
        self.save_log_config(ctx.guild.id)

        await interface.reply(ctx, f'Deleted log channel {channel.mention}.')

    @log.command()
    async def channels(self, ctx: commands.Context[commands.Bot]) -> None:
        assert(isinstance(ctx.author, discord.Member))
        if not ctx.author.guild_permissions.manage_channels:
            await interface.reply(ctx, 'You are not allowed to manage channels in this server.')
            return

        assert(ctx.guild)
        if ctx.guild.id not in self.configs:
            await interface.reply(ctx, 'There are no log channels in this server.')
            return

        channel_ids = list(self.configs[ctx.guild.id])
        mentions = [f'<#{channel_id}>' for channel_id in channel_ids]
        await interface.reply(ctx, f'Log channels: {', '.join(mentions)}.')

    @create.error
    async def create_error(self, ctx: commands.Context[commands.Bot], error: commands.CommandError) -> None:
        # placeholder error messages :P
        if isinstance(error, commands.MissingRequiredArgument):
            await interface.reply(ctx, "you didn't specify a channel")
        else:
            await interface.reply(ctx, 'some other error')

    async def _cmd_get_channel(self, ctx: commands.Context[commands.Bot], given_channel: Optional[discord.TextChannel]) -> discord.TextChannel | None:
        assert(ctx.guild)
        if ctx.guild.id not in self.configs:
            await interface.reply(ctx, 'There are no log channels in this server. You can create one with `log create`.')
            return None

        if given_channel is None:
            if len(self.configs[ctx.guild.id]) == 1:
                channel_id = list(self.configs[ctx.guild.id])[0]
                channel = ctx.guild.get_channel(channel_id)
                if channel is None:
                    await interface.reply(ctx, f"Somehow, <#{channel_id}> ({channel_id}) doesn't exist.")
                    return
            else:
                channel = ctx.channel
                if channel.id not in self.configs[ctx.guild.id]:
                    await interface.reply(ctx, 'This channel is not a log channel. You can create one with `log create`.')
                    return None
        else:
            channel = given_channel
            if channel.id not in self.configs[ctx.guild.id]:
                await interface.reply(ctx, 'That channel is not a log channel. You can create one with `log create`.')
                return None

        if channel.guild != ctx.guild:
            await interface.reply(ctx, "That channel isn't in this server.")
            return None

        assert(isinstance(channel, discord.TextChannel))
        return channel

    async def _cmd_poke_item(self, ctx: commands.Context[commands.Bot], given_channel: Optional[discord.TextChannel], value: bool, *items: str) -> None:
        assert(ctx.guild)
        channel = await self._cmd_get_channel(ctx, given_channel)
        if channel is None:
            return

        if not await self._cmd_check_permission(ctx, channel):
            return

        ignored: list[str] = []
        processed: list[str] = []
        for item in items:
            if item not in VALID_LOG_ITEMS:
                ignored.append(item)
            else:
                self.configs[ctx.guild.id][channel.id][item] = value
                processed.append(item)

        changed = ', '.join(processed)
        text: list[str] = []
        if processed:
            if value:
                text.append(f'Successfully enabled {changed}.')
            else:
                text.append(f'Successfully disabled {changed}.')
        else:
            text.append('No items changed.')

        if ignored:
            text.append(f'Ignored invalid items: {', '.join(ignored)}.')

        self.save_log_config(ctx.guild.id)
        await interface.reply(ctx, ' '.join(text))

    @log.command()
    async def enable(self, ctx: commands.Context[commands.Bot], given_channel: Optional[discord.TextChannel], *items: str) -> None:
        await self._cmd_poke_item(ctx, given_channel, True, *items)

    @log.command()
    async def disable(self, ctx: commands.Context[commands.Bot], given_channel: Optional[discord.TextChannel], *items: str) -> None:
        await self._cmd_poke_item(ctx, given_channel, False, *items)

    @log.command()
    async def get(self, ctx: commands.Context[commands.Bot], given_channel: Optional[discord.TextChannel]) -> None:
        assert(ctx.guild)
        channel = await self._cmd_get_channel(ctx, given_channel)
        if channel is None:
            return

        if not await self._cmd_check_permission(ctx, channel):
            return

        items = [key for key, value in self.configs[ctx.guild.id][channel.id].items() if value]
        if not items:
            items.append('None')

        await interface.reply(ctx, f'Enabled logs for {channel.mention}: {', '.join(items)}.')


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
