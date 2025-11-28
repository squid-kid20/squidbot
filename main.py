# SPDX-License-Identifier: AGPL-3.0-only

import discord
from discord.ext import commands

with open('bot_token.txt', 'r') as file:
    bot_token = file.readlines()[0].strip()

class BotClient(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix='!', intents=intents)

    async def on_ready(self):
        print(f'Logged on as {self.user}.')

        await self.load_extension('cogs.test')
        await self.load_extension('cogs.logs')

    async def on_message(self, message):
        print(f'Message from {message.author}: {message.content}')

        await self.process_commands(message)

intents = discord.Intents.all()

client = BotClient()
client.run(bot_token)
