# Discord Bot

This is a Discord bot focused on logging and moderation, with some additional
functions.

## Requirements

### Dependencies

> _Optional but recommended:_ Create a virtual environment.
>
> ```shell
> python -m venv env
> ```
>
> Enter it using `.\env\Scripts\activate` on Windows, or `source env/bin/activate`
> on UNIX-likes.

Install `discord.py`.

```shell
python -m pip install -U discord.py
```

### Bot Account

Copy the bot token into `bot_token.txt`, a file in the same directory as
`main.py`.

The bot should have the following intents: Presence, Server Members, and
Message Content.

## License

This repository is licensed under AGPLv3 only, and no later version. See
[`LICENSE.md`](LICENSE.md) for further details.