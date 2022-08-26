from __future__ import annotations

from typing import TYPE_CHECKING

from botus_receptus.sqlalchemy import Snowflake
from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, func, select
from sqlalchemy.dialects.postgresql import insert

from ..exceptions import InvalidVersionError
from .base import (
    Base,
    Mapped,
    mapped_column,
    mixin_column,
    model,
    model_mixin,
    relationship,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import discord
    from sqlalchemy.ext.asyncio import AsyncSession


@model
class BibleVersion(Base):
    __tablename__ = 'bible_versions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    command: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    abbr: Mapped[str] = mapped_column(String, nullable=False)
    service: Mapped[str] = mapped_column(String, nullable=False)
    service_version: Mapped[str] = mapped_column(String, nullable=False)
    rtl: Mapped[bool | None] = mapped_column(Boolean)
    books: Mapped[int] = mapped_column(BigInteger, nullable=False)

    async def set_for_user(
        self, session: AsyncSession, user: discord.User | discord.Member, /
    ) -> None:
        await session.execute(
            insert(UserPref)
            .values(user_id=user.id, bible_id=self.id)
            .on_conflict_do_update(
                index_elements=['user_id'], set_={'bible_id': self.id}
            )
        )

    async def set_for_guild(
        self, session: AsyncSession, guild: discord.Guild, /
    ) -> None:
        await session.execute(
            insert(GuildPref)
            .values(guild_id=guild.id, bible_id=self.id)
            .on_conflict_do_update(
                index_elements=['guild_id'], set_={'bible_id': self.id}
            )
        )

    @staticmethod
    async def get_all(
        session: AsyncSession,
        /,
        *,
        ordered: bool = False,
        search_term: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[BibleVersion]:
        stmt = select(BibleVersion)

        if ordered:
            stmt = stmt.order_by(BibleVersion.command.asc())

        if limit:
            stmt = stmt.limit(limit)

        if search_term is not None:
            search_term = search_term.lower()
            stmt = stmt.filter(
                func.lower(BibleVersion.command).startswith(
                    search_term, autoescape=True
                )
                | func.lower(BibleVersion.abbr).startswith(search_term, autoescape=True)
                | func.lower(BibleVersion.name).contains(search_term, autoescape=True)
            )

        result = await session.scalars(stmt)

        for version in result:
            yield version

    @staticmethod
    async def get_by_command(session: AsyncSession, command: str, /) -> BibleVersion:
        bible: BibleVersion | None = (
            await session.scalars(
                select(BibleVersion).filter(BibleVersion.command == command)
            )
        ).first()

        if bible is None:
            raise InvalidVersionError(command)

        return bible

    @staticmethod
    async def get_by_abbr(session: AsyncSession, abbr: str, /) -> BibleVersion | None:
        return (
            await session.scalars(
                select(BibleVersion).filter(BibleVersion.command.ilike(abbr))
            )
        ).first()

    @staticmethod
    async def get_for_user(
        session: AsyncSession,
        user: discord.User | discord.Member,
        guild: discord.Guild | None,
        /,
    ) -> BibleVersion:
        user_pref = await session.get(UserPref, user.id)

        if user_pref is not None and user_pref.bible_version is not None:
            return user_pref.bible_version

        if guild is not None:
            guild_pref = await session.get(GuildPref, guild.id)

            if guild_pref is not None and guild_pref.bible_version is not None:
                return guild_pref.bible_version

        return await BibleVersion.get_by_command(session, 'esv')


@model_mixin
class _BibleVersionMixin(Base):
    bible_id: Mapped[int | None] = mixin_column(
        lambda: mapped_column(Integer, ForeignKey('bible_versions.id'))
    )
    bible_version: Mapped[BibleVersion | None] = relationship(
        BibleVersion, lazy='joined', uselist=False
    )


@model
class UserPref(_BibleVersionMixin):
    __tablename__ = 'user_prefs'

    user_id: Mapped[int] = mapped_column(Snowflake, primary_key=True, init=True)


@model
class GuildPref(_BibleVersionMixin):
    __tablename__ = 'guild_prefs'

    guild_id: Mapped[int] = mapped_column(Snowflake, primary_key=True, init=True)
