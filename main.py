# SPDX-License-Identifier: AGPL-3.0-only

import discord
from discord.ext import commands
from typing import Any, Callable


class BotClient(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        allowed_mentions = discord.AllowedMentions.none()
        super().__init__(
            command_prefix='!',
            intents=intents,
            allowed_mentions=allowed_mentions,
            enable_debug_events=True, # needed for on_socket_raw_receive
        )

        self._create_message_hooks: list[Callable[[dict[str, Any]], None]] = []

        original_create_message = self._connection.create_message
        def interdicted_create_message(self2, *, channel, data):
            """Intercept the create_message function internally used in discord.py.

            create_message gets called when a message is fetched by us or when
            we send a message.
            """
            for hook in self._create_message_hooks:
                hook(data)
            return original_create_message.__get__(self2)(channel=channel, data=data)
        self._connection.create_message = interdicted_create_message.__get__(self._connection)

    def register_create_message_hook(self, hook: Callable[[dict[str, Any]], None], /) -> None:
        self._create_message_hooks.append(hook)

    async def on_ready(self):
        print(f'Logged on as {self.user}.')

        await self.load_extension('cogs.test')
        await self.load_extension('cogs.logs')
        await self.load_extension('cogs.history')

    async def on_message(self, message: discord.Message):
        print(f'Message from {message.author}: {message.content}')

        await self.process_commands(message)

if __name__ == '__main__':
    with open('bot_token.txt', 'r') as file:
        bot_token = file.readlines()[0].strip()

    client = BotClient()
    client.run(bot_token)
