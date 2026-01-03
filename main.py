# SPDX-License-Identifier: AGPL-3.0-only

import discord
import inspect
import json
from discord.ext import commands
from typing import Any, Callable, TypedDict


class BotConfig(TypedDict):
    # All history is disabled for these guilds.
    history_disabled_guilds: list[int]

    # History fetching is disabled, but new messages will still be recorded.
    history_fetching_disabled_guilds: list[int]

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

        self._configs: BotConfig = {
            'history_disabled_guilds': [],
            'history_fetching_disabled_guilds': [],
        }

        try:
            with open('config.json', 'r') as file:
                self._configs = json.load(file)
        except FileNotFoundError:
            with open('config.json', 'w') as file:
                json.dump(self._configs, file)

        self._create_message_hooks: list[Callable[[dict[str, Any]], None]] = []

        original_create_message = self._connection.create_message
        def interdicted_create_message(self2, *, channel, data):
            """Intercept the create_message function internally used in discord.py.

            create_message gets called when a message is fetched by us or when
            we send a message. But we make sure our hooks don't run when
            the call is the result of us sending a message.
            """
            stack = inspect.stack()
            caller = stack[1]
            # https://github.com/Rapptz/discord.py/blob/master/discord/abc.py
            is_send = caller.function == 'send' and caller.filename.endswith('abc.py')

            if not is_send:
                for hook in self._create_message_hooks:
                    hook(data)

            return original_create_message.__get__(self2)(channel=channel, data=data)
        self._connection.create_message = interdicted_create_message.__get__(self._connection)

    def register_create_message_hook(self, hook: Callable[[dict[str, Any]], None], /) -> None:
        self._create_message_hooks.append(hook)

    def history_enabled(self, guild_id: int) -> bool:
        return guild_id not in self._configs['history_disabled_guilds']

    def history_fetching_enabled(self, guild_id: int) -> bool:
        if not self.history_enabled(guild_id):
            return False

        return guild_id not in self._configs['history_fetching_disabled_guilds']

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
