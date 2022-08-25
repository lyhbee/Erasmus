from __future__ import annotations

from typing import TYPE_CHECKING

from botus_receptus.sqlalchemy import Snowflake
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    asc,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert

from ..exceptions import InvalidVersionError
from .base import Base, Column, Mapped, mixin_column, model, model_mixin, relationship

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import discord
    from sqlalchemy.ext.asyncio import AsyncSession


@model
class BibleVersion(Base):
    __tablename__ = 'bible_versions'

    id: Mapped[int] = Column(Integer, primary_key=True)
    command: Mapped[str] = Column(String, unique=True, nullable=False)
    name: Mapped[str] = Column(String, nullable=False)
    abbr: Mapped[str] = Column(String, nullable=False)
    service: Mapped[str] = Column(String, nullable=False)
    service_version: Mapped[str] = Column(String, nullable=False)
    rtl: Mapped[bool | None] = Column(Boolean)
    books: Mapped[int] = Column(BigInteger, nullable=False)

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
            stmt = stmt.order_by(asc(BibleVersion.command))

        if limit:
            stmt = stmt.limit(limit)

        if search_term is not None:
            search_term = search_term.lower()
            stmt = stmt.where(
                or_(
                    func.lower(BibleVersion.command).startswith(
                        search_term, autoescape=True
                    ),
                    func.lower(BibleVersion.abbr).startswith(
                        search_term, autoescape=True
                    ),
                    func.lower(BibleVersion.name).contains(
                        search_term, autoescape=True
                    ),
                )
            )

        result = await session.scalars(stmt)

        for version in result:
            yield version

    @staticmethod
    async def get_by_command(session: AsyncSession, command: str, /) -> BibleVersion:
        bible: BibleVersion | None = (
            await session.scalars(
                select(BibleVersion).where(BibleVersion.command == command)
            )
        ).first()

        if bible is None:
            raise InvalidVersionError(command)

        return bible

    @staticmethod
    async def get_by_abbr(session: AsyncSession, abbr: str, /) -> BibleVersion | None:
        return (
            await session.scalars(
                select(BibleVersion).where(BibleVersion.command.ilike(abbr))
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
        lambda: Column(Integer, ForeignKey('bible_versions.id'))
    )
    bible_version: Mapped[BibleVersion | None] = mixin_column(
        lambda: relationship(BibleVersion, lazy='joined', uselist=False)
    )


@model
class UserPref(_BibleVersionMixin):
    __tablename__ = 'user_prefs'

    user_id: Mapped[int] = Column(Snowflake, primary_key=True, init=True)


@model
class GuildPref(_BibleVersionMixin):
    __tablename__ = 'guild_prefs'

    guild_id: Mapped[int] = Column(Snowflake, primary_key=True, init=True)
