# SPDX-License-Identifier: AGPL-3.0-only

import datetime
import discord
import interface
import json
import os
import pathlib
from discord.ext import commands


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

        config = self.configs[str(message.guild.id)]

        for channel_id, channel_config in config.items():
            if not channel_config.get('message_delete', False):
                continue
            channel = self.bot.get_channel(int(channel_id))
            if not isinstance(channel, discord.TextChannel):
                continue
            if channel.guild != message.guild:
                continue

            embed = discord.Embed(
                colour=self.get_colour(message.author),
                description=message.content,
            ).set_author(
                name=message.author.display_name,
                icon_url=message.author.display_avatar.url,
            ).set_footer(
                text=self.id_tags(
                    user_id=message.author.id,
                    message_id=message.id,
                    channel_id=message.channel.id,
                ),
            )
            reltime = self.relative_time(message.created_at)

            await channel.send(
                f'**\N{WASTEBASKET} MESSAGE DELETED**\n'
                f'Sent {reltime} by {message.author.mention} in {message.channel.mention}',
                embed=embed,
            )

            if message.attachments:
                files = self.get_downloaded_attachments(message)
                if files:
                    await channel.send(
                        f'\N{PAPERCLIP} _Attachments of message {message.id}:_',
                        files=files,
                    )
                else:
                    await channel.send(
                        f'\N{PAPERCLIP} _Attachments of message {message.id} could not be found._',
                    )

    async def download_attachments(self, message: discord.Message, /) -> None:
        """Download attachments from a message."""
        if message.guild is None:
            return
        path = f'attachments/{message.guild.id}/{message.channel.id}/{message.id}'
        os.makedirs(path, exist_ok=True)
        for attachment in message.attachments:
            await attachment.save(fp=pathlib.Path(path, f'{attachment.id}-{attachment.filename}'))

    def get_downloaded_attachments(self, message: discord.Message, /) -> list[discord.File]:
        files: list[discord.File] = []
        if message.guild is None:
            return files
        path = f'attachments/{message.guild.id}/{message.channel.id}/{message.id}'
        if not os.path.exists(path):
            return files

        for filename in os.listdir(path):
            files.append(
                discord.File(
                    fp=pathlib.Path(path, filename),
                    filename=filename.split('-', 1)[1],
                ),
            )
        return files

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not isinstance(before.channel, discord.abc.GuildChannel):
            return
        if before.guild is None:
            return
        if str(before.guild.id) not in self.configs:
            return

        config = self.configs[str(before.guild.id)]

        for channel_id, channel_config in config.items():
            if not channel_config.get('message_edit', False):
                continue
            channel = self.bot.get_channel(int(channel_id))
            if not isinstance(channel, discord.TextChannel):
                continue
            if channel.guild != before.guild:
                continue

            # FIXME: handle 4000 character limit
            embed = discord.Embed(
                colour=self.get_colour(before.author),
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
                text=self.id_tags(
                    user_id=before.author.id,
                    message_id=before.id,
                    channel_id=before.channel.id,
                ),
            )

            reltime = self.relative_time(before.created_at)
            await channel.send(
                f'**\N{MEMO} MESSAGE EDITED**\n'
                f'Sent {reltime} by {before.author.mention} in {before.channel.mention}',
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
        self, *,
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

    def get_colour(self, user: discord.User | discord.Member, /) -> discord.Colour | None:
        if user.colour == discord.Colour.default():
            return None
        return user.colour

    def relative_time(self, dt: datetime.datetime, /) -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = now - dt
        seconds = int(delta.total_seconds())

        if seconds == 0:
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


async def setup(bot):
    await bot.add_cog(Logs(bot))
