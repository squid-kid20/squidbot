# SPDX-License-Identifier: AGPL-3.0-only

import interface
from discord.ext import commands

class Test(commands.Cog):
    @commands.command()
    async def test(self, ctx: commands.Context[commands.Bot]):
        await interface.reply(ctx, 'test')

async def setup(bot: commands.Bot):
    await bot.add_cog(Test(bot))
