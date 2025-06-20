# SPDX-License-Identifier: AGPL-3.0-only

from discord.ext import commands

class Test(commands.Cog):
    @commands.command()
    async def test(self, ctx):
        await ctx.send('test')

async def setup(bot):
    await bot.add_cog(Test(bot))
