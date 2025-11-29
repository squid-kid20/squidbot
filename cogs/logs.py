# SPDX-License-Identifier: AGPL-3.0-only

import discord
import interface
import json
import os
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

            # TODO: handle attachments
            embed = discord.Embed(
                colour=self.get_colour(message.author),
                description=message.content, # FIXME: handle 4000 character messages
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

            await channel.send(
                f'**\N{WASTEBASKET} MESSAGE DELETED (in {message.channel.mention})**',
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

    def get_colour(self, user: discord.User | discord.Member) -> discord.Colour | None:
        if user.colour == discord.Colour.default():
            return None
        return user.colour


async def setup(bot):
    await bot.add_cog(Logs(bot))
