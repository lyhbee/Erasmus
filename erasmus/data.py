from __future__ import annotations

from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypedDict

import orjson
from attrs import define
from botus_receptus import re
from more_itertools import unique_everseen

from .exceptions import BookNotUnderstoodError, ReferenceNotUnderstoodError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from re import Match, Pattern
    from typing_extensions import Self

    import discord


class BookDict(TypedDict):
    name: str
    osis: str
    paratext: str | None
    alt: list[str]
    section: int | Literal['DC']


with (Path(__file__).resolve().parent / 'data' / 'books.json').open() as f:
    _books_data: Final[list[BookDict]] = orjson.loads(f.read())

# Inspired by
# https://github.com/TehShrike/verse-reference-regex/blob/master/create-regex.js
_book_re: Final = re.compile(
    re.named_group('book')(
        re.either(
            *re.escape_all(
                unique_everseen(
                    chain.from_iterable(
                        [
                            [book['name'], book['osis']] + book['alt']
                            for book in _books_data
                        ]
                    )
                )
            )
        )
    ),
    re.optional(re.DOT),
)

_version_group: Final = re.named_group('version')
_one_or_more_digit: Final = re.one_or_more(re.DIGIT)
_colon: Final = re.combine(
    re.any_number_of(re.WHITESPACE), ':', re.any_number_of(re.WHITESPACE)
)

_reference_re: Final = re.compile(
    _book_re,
    re.one_or_more(re.WHITESPACE),
    re.named_group('chapter_start')(_one_or_more_digit),
    _colon,
    re.named_group('verse_start')(_one_or_more_digit),
    re.optional(
        re.any_number_of(re.WHITESPACE),
        '[',
        re.DASH,
        '\u2013',
        '\u2014',
        ']',
        re.any_number_of(re.WHITESPACE),
        re.optional(re.named_group('chapter_end')(_one_or_more_digit), _colon),
        re.named_group('verse_end')(_one_or_more_digit),
    ),
    flags=re.IGNORECASE,
)

_reference_with_version_re: Final = re.compile(
    _reference_re,
    re.optional(
        re.any_number_of(re.WHITESPACE),
        _version_group(re.one_or_more(re.ALPHANUMERICS)),
    ),
    flags=re.IGNORECASE,
)

_reference_or_bracketed_with_version_re: Final = re.compile(
    re.optional(
        re.named_group('bracket')(re.LEFT_BRACKET, re.any_number_of(re.WHITESPACE))
    ),
    _reference_re,
    re.if_group(
        'bracket',
        re.group(
            re.optional(
                re.one_or_more(re.WHITESPACE),
                _version_group(re.one_or_more(re.ALPHANUMERICS)),
            ),
            re.any_number_of(re.WHITESPACE),
            re.RIGHT_BRACKET,
        ),
    ),
    flags=re.IGNORECASE,
)

_bracketed_reference_with_version_re: Final = re.compile(
    re.LEFT_BRACKET,
    re.any_number_of(re.WHITESPACE),
    _reference_with_version_re,
    re.any_number_of(re.WHITESPACE),
    re.RIGHT_BRACKET,
    flags=re.IGNORECASE,
)

_search_reference_re: Final = re.compile(
    re.START, _reference_re, re.END, flags=re.IGNORECASE
)

_search_reference_with_version_re: Final = re.compile(
    re.START, _reference_with_version_re, re.END, flags=re.IGNORECASE
)

_book_input_map: Final[dict[str, str]] = {}
_book_data_map: Final[dict[str, BookDict]] = {}
_book_mask_map: Final[dict[str, int | Literal['DC']]] = {}

for _book in _books_data:
    for input_string in [_book['name'], _book['osis']] + _book['alt']:
        _book_input_map[input_string.lower()] = _book['name']
        _book_data_map[input_string.lower()] = _book
    _book_mask_map[_book['name']] = _book['section']


def get_book_data(book_name_or_abbr: str, /) -> BookDict:
    book = _book_data_map.get(book_name_or_abbr.lower())

    if book is None:
        raise BookNotUnderstoodError(book_name_or_abbr)

    return book


def get_books_for_mask(book_mask: int, /) -> Iterator[BookDict]:
    if book_mask & 1:
        yield _book_data_map['genesis']
    if book_mask & 2:
        yield _book_data_map['matthew']

    for book in _books_data:
        if book['section'] == 1 or book['section'] == 2 or book['section'] == 'DC':
            continue

        if book_mask & book['section']:
            yield book


@define(frozen=True)
class Verse:
    chapter: int
    verse: int

    def __str__(self, /) -> str:
        return f'{self.chapter}:{self.verse}'


@define(frozen=True)
class VerseRange:
    book: str
    start: Verse
    end: Verse | None
    version: str | None
    book_mask: int | Literal['DC']
    osis: str
    paratext: str | None

    @property
    def verses(self, /) -> str:
        verse = str(self.start)

        if self.end is not None:
            if self.end.chapter == self.start.chapter:
                verse += f'-{self.end.verse}'
            else:
                verse += f'-{self.end}'

        return verse

    def __str__(self, /) -> str:
        return f'{self.book} {self.verses}'

    @classmethod
    def create(
        cls,
        book: str,
        start: Verse,
        end: Verse | None = None,
        version: str | None = None,
        /,
    ) -> Self:
        data = get_book_data(book)

        return cls(
            data['name'],
            start,
            end,
            version,
            data['section'],
            data['osis'],
            data['paratext'],
        )

    @classmethod
    def from_string(cls, verse: str, /) -> Self:
        if (match := _search_reference_re.match(verse)) is None:
            raise ReferenceNotUnderstoodError(verse)

        return cls.from_match(match)

    @classmethod
    def from_string_with_version(cls, verse: str, /) -> Self:
        if (match := _search_reference_with_version_re.match(verse)) is None:
            raise ReferenceNotUnderstoodError(verse)

        return cls.from_match(match)

    @classmethod
    def from_match(cls, match: Match[str], /) -> Self:
        groups = match.groupdict()

        chapter_start_int = int(groups['chapter_start'])
        start = Verse(chapter_start_int, int(groups['verse_start']))

        end: Verse | None = None
        end_str = groups['verse_end']

        if end_str is not None:
            end_int = int(end_str)
            chapter_end_int = chapter_start_int

            chapter_end_str = groups['chapter_end']
            if chapter_end_str is not None:
                chapter_end_int = int(chapter_end_str)

            end = Verse(chapter_end_int, end_int)

        version: str | None = groups.get('version')

        return cls.create(groups['book'], start, end, version)

    @classmethod
    def get_all_from_string(
        cls, string: str, /, *, only_bracketed: bool = False
    ) -> list[Self | Exception]:
        ranges: list[VerseRange | Exception] = []
        lookup_pattern: Pattern[str]

        if only_bracketed:
            lookup_pattern = _bracketed_reference_with_version_re
        else:
            lookup_pattern = _reference_or_bracketed_with_version_re

        if (match := lookup_pattern.search(string)) is not None:
            while match:
                try:
                    ranges.append(cls.from_match(match))
                except Exception as exc:  # noqa: PIE786
                    ranges.append(exc)

                match = lookup_pattern.search(string, match.end())

        return ranges

    @classmethod
    async def transform(cls, itx: discord.Interaction, value: str, /) -> Self:
        return cls.from_string_with_version(value)


@define(frozen=True)
class Passage:
    text: str
    range: VerseRange
    version: str | None = None

    @property
    def citation(self, /) -> str:
        if self.version is not None:
            return f'{self.range} ({self.version})'
        else:
            return str(self.range)

    def __str__(self, /) -> str:
        return f'{self.text}\n\n{self.citation}'


@define(frozen=True)
class SearchResults:
    verses: list[Passage]
    total: int

    def __iter__(self, /) -> Iterator[Passage]:
        return self.verses.__iter__()
