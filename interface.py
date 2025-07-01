# SPDX-License-Identifier: AGPL-3.0-only

"""
This module is a wrapper around all discord.py functions,
so it can be mocked for testing.
"""

from discord.ext import commands

async def send(ctx: commands.Context, content: str) -> None:
    """Sends a message to the given context with only text content."""
    await ctx.send(content)

async def reply(ctx: commands.Context, content: str) -> None:
    """Sends a reply to the given context with only text content."""
    await ctx.send(content, reference=ctx.message)