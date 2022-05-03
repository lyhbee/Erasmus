from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any, Final, cast

import discord
import discord.http
import pendulum
from botus_receptus import exceptions, formatting, sqlalchemy as sa, topgg, utils
from botus_receptus.interactive_pager import CannotPaginate, CannotPaginateReason
from discord import app_commands
from discord.ext import commands
from pendulum.period import Period

from .config import Config
from .db import Session
from .exceptions import ErasmusError
from .help import HelpCommand

if TYPE_CHECKING:
    from .cogs.bible import Bible

_log: Final = logging.getLogger(__name__)

_extensions: Final = ('admin', 'bible', 'confession', 'creeds', 'misc')


_description: Final = '''
Erasmus:
--------

You can look up all verses in a message one of two ways:

* Mention me in the message
* Surround verse references in []
    ex. [John 3:16] or [John 3:16 NASB]

'''


discord.http._set_api_version(9)


class Erasmus(sa.AutoShardedBot, topgg.AutoShardedBot):
    config: Config

    def __init__(self, config: Config, /, *args: Any, **kwargs: Any) -> None:
        kwargs['help_command'] = HelpCommand(
            paginator=formatting.Paginator(),
            command_attrs={
                'brief': 'List commands for this bot or get help for commands',
                'cooldown': commands.CooldownMapping.from_cooldown(
                    5, 30.0, commands.BucketType.user
                ),
            },
        )
        kwargs['description'] = _description
        kwargs['intents'] = discord.Intents(guilds=True, reactions=True, messages=True)
        kwargs['allowed_mentions'] = discord.AllowedMentions(
            roles=False, everyone=False, users=True
        )

        super().__init__(config, *args, sessionmaker=Session, **kwargs)

        self.tree.error(self.on_app_command_error)

    @property
    def bible_cog(self) -> 'Bible':
        return self.cogs['Bible']  # type: ignore

    async def setup_hook(self) -> None:
        await super().setup_hook()

        for extension in _extensions:
            try:
                await self.load_extension(f'erasmus.cogs.{extension}')
            except Exception:
                _log.exception('Failed to load extension %s.', extension)

        await self.sync_app_commands()

        _log.info(
            'Global commands: '
            f'{list(self.tree._global_commands.keys())!r}'  # type: ignore
        )

        for guild_id, _commands in self.tree._guild_commands.items():  # type: ignore
            _log.info(f'Commands for {guild_id}: {list(_commands)!r}')  # type: ignore

    async def process_commands(self, message: discord.Message, /) -> None:
        if message.author.bot:
            return

        ctx = await self.get_context(message)

        if ctx.command is None:
            try:
                await self.bible_cog.lookup_from_message(ctx, message)
            except commands.CommandError as exc:
                self.dispatch('command_error', ctx, exc)

            return

        await self.invoke(ctx)

    async def on_ready(self, /) -> None:
        await self.change_presence(
            activity=discord.Game(name=f'| {self.default_prefix}help')
        )

        user = self.user
        assert user is not None
        _log.info('Erasmus ready. Logged in as %s %s', user.name, user.id)

        await super().on_ready()

    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        _, exception, _ = sys.exc_info()

        if exception is None:
            return

        _log.exception(
            f'Exception occurred handling an event:\n\tEvent: {event_method}',
            exc_info=exception,
            stack_info=True,
        )

    async def on_command_error(
        self,
        context: commands.Context[Any],
        exception: Exception,
        /,
    ) -> None:
        if (
            isinstance(
                exception,
                (
                    commands.CommandInvokeError,
                    commands.BadArgument,
                    commands.ConversionError,
                ),
            )
            and exception.__cause__ is not None
        ):
            exception = cast(commands.CommandError, exception.__cause__)

        if isinstance(exception, ErasmusError):
            # All of these are handled in their respective cogs
            return

        message = 'An error occurred'

        match exception:
            case commands.NoPrivateMessage():
                message = 'This command is not available in private messages'
            case commands.CommandOnCooldown():
                message = ''
                if exception.type == commands.BucketType.user:
                    message = 'You have used this command too many times.'
                elif exception.type == commands.BucketType.channel:
                    message = (
                        f'`{context.prefix}{context.invoked_with}` has been used too '
                        'many times in this channel.'
                    )
                retry_period: Period = (
                    pendulum.now()
                    .add(seconds=int(exception.retry_after))
                    .diff()  # type: ignore
                )
                message = (
                    f'{message} You can retry again in '
                    f'{retry_period.in_words()}.'  # type: ignore
                )
            case commands.MissingPermissions():
                message = 'You do not have the correct permissions to run this command'
            case exceptions.OnlyDirectMessage():
                message = 'This command is only available in private messages'
            case commands.MissingRequiredArgument():
                message = f'The required argument `{exception.param.name}` is missing'
            case CannotPaginate():
                match exception.reason:
                    case CannotPaginateReason.embed_links:
                        message = 'I need the "Embed Links" permission'
                    case CannotPaginateReason.send_messages:
                        message = 'I need the "Send Messages" permission'
                    case CannotPaginateReason.add_reactions:
                        message = 'I need the "Add Reactions" permission'
                    case CannotPaginateReason.read_message_history:
                        message = 'I need the "Read Message History" permission'
            case _:
                qualified_name = (
                    'NO COMMAND'
                    if context.command is None
                    else context.command.qualified_name
                )
                content = (
                    'NO MESSAGE' if context.message is None else context.message.content
                )
                invoked_by = f'{context.author.display_name} ({context.author.id})'

                _log.exception(
                    'Exception occurred processing a message:\n'
                    f'\tCommand: {qualified_name}\n'
                    f'\tInvoked by: {invoked_by}\n'
                    f'\tJump URL: {context.message.jump_url}\n'
                    f'\tInvoked with: {content}',
                    exc_info=exception,
                    stack_info=True,
                )

        await utils.send_embed_error(
            context, description=formatting.escape(message, mass_mentions=True)
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        /,
    ) -> None:
        if (
            isinstance(
                error, (app_commands.CommandInvokeError, app_commands.TransformerError)
            )
            and error.__cause__ is not None
        ):
            error = cast(Exception, error.__cause__)

        if isinstance(error, ErasmusError):
            # All of these are handled in their respective cogs
            return

        message = 'An error occurred'

        match error:
            case commands.NoPrivateMessage():
                message = 'This command is not available in private messages'
            case app_commands.CommandOnCooldown():
                retry_period: Period = (
                    pendulum.now()
                    .add(seconds=int(error.retry_after))
                    .diff()  # type: ignore
                )
                message = (
                    'You have used this command too many times. You can retry again in '
                    f'{retry_period.in_words()}.'  # type: ignore
                )
            case app_commands.MissingPermissions():
                message = 'You do not have permission to run this command'
            case CannotPaginate():
                match error.reason:
                    case CannotPaginateReason.embed_links:
                        message = 'I need the "Embed Links" permission'
                    case CannotPaginateReason.send_messages:
                        message = 'I need the "Send Messages" permission'
                    case CannotPaginateReason.add_reactions:
                        message = 'I need the "Add Reactions" permission'
                    case CannotPaginateReason.read_message_history:
                        message = 'I need the "Read Message History" permission'
            case _:
                qualified_name = (
                    'NO INTERACTION'
                    if interaction.command is None
                    else interaction.command.qualified_name
                )
                jump_url = (
                    'NONE'
                    if interaction.message is None
                    else interaction.message.jump_url
                )
                invoked_by = f'{interaction.user.display_name} ({interaction.user.id})'

                _log.exception(
                    'Exception occurred in interaction:\n'
                    f'\tInteraction: {qualified_name}\n'
                    f'\tInvoked by: {invoked_by}\n'
                    f'\tJump URL: {jump_url}',
                    exc_info=error,
                    stack_info=True,
                )

        await utils.send_embed_error(interaction, description=message)


__all__: Final = ('Erasmus',)
