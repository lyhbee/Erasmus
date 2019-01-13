from __future__ import annotations

from typing import List, Iterable, Tuple
from discord.ext import commands
from more_itertools import unique_everseen

_roman_pairs = tuple(
    zip(
        ('M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I'),
        (1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1),
    )
)


def int_to_roman(number: int) -> str:
    numerals = []  # type: List[str]

    for letter, value in _roman_pairs:
        count, number = divmod(number, value)
        numerals.append(letter * count)

    return ''.join(numerals)


def roman_to_int(numerals: str) -> int:
    numerals = numerals.upper()
    index = result = 0

    for letter, value in _roman_pairs:
        while numerals[index : index + len(letter)] == letter:
            result += value
            index += len(letter)

    return result


class HelpFormatter(commands.HelpFormatter):
    def _get_command_title(self, name: str, command: commands.Command) -> str:
        return ', '.join(
            map(lambda s: f'{self.clean_prefix}{s}', [name] + command.aliases)
        )

    async def filter_command_list(self) -> Iterable[Tuple[str, commands.Command]]:
        iterable = await super().filter_command_list()
        return unique_everseen(iterable, lambda x: x[1])

    async def format(self) -> List[str]:
        self._paginator = commands.Paginator()
        add_line = self._paginator.add_line

        if isinstance(self.command, commands.Command):
            if self.command.brief:
                add_line(self.command.brief, empty=True)

            signature_parts = self.get_command_signature().split(' ')

            if '|' in signature_parts[0]:
                names = signature_parts[0][2:-1].split('|')
            else:
                names = [signature_parts[0][1:]]

            add_line('Usage:')
            add_line('------')

            for name in names:
                add_line(
                    '    '
                    + signature_parts[0][0]
                    + name
                    + ' '
                    + ' '.join(signature_parts[1:])
                )

            if self.command.help:
                if self.command.help[0] != '\n':
                    add_line()
                add_line(self.command.help.format(prefix=self.clean_prefix))

            self._paginator.close_page()
            return self._paginator.pages

        if isinstance(self.command, commands.Bot):
            add_line(self.command.description, empty=True)

            filtered = await self.filter_command_list()
            filtered = sorted(filtered)

            add_line('Commands:')
            add_line('---------', empty=True)

            for name, command in filtered:
                add_line(self._get_command_title(name, command))
                add_line('    ' + command.short_doc, empty=True)

            add_line(f'{self.clean_prefix}<version>')
            add_line(
                '    Look up a verse in a specific version (see '
                f'{self.clean_prefix}versions)',
                empty=True,
            )
            add_line(f'{self.clean_prefix}s<version>')
            add_line(
                '    Search for terms in a specific version (see '
                f'{self.clean_prefix}versions)',
                empty=True,
            )

        add_line()
        add_line(
            f'''You can type the following for more information on a command:

    {self.clean_prefix}{self.context.invoked_with} <command>'''
        )

        return self._paginator.pages
