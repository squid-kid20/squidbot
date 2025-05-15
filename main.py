# SPDX-License-Identifier: AGPL-3.0-only

import discord

with open('bot_token.txt', 'r') as file:
    bot_token = file.readlines()[0].strip()

class BotClient(discord.Client):
    async def on_ready(self):
        print(f'Logged on as {self.user}.')

    async def on_message(self, message):
        print(f'Message from {message.author}: {message.content}')

intents = discord.Intents.all()

client = BotClient(intents=intents)
client.run(bot_token)
