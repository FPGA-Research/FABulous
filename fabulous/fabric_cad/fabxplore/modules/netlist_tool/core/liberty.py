"""Liberty text manipulation helpers.

This module modifies Liberty library text before Yosys consumes it. The handler
supports removing standard-cell blocks, changing direct cell ``area`` values,
and appending additional cell definitions from Liberty fragments.
"""

import re
from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.models import (
    PdkInputConfig,
)


@dataclass(frozen=True)
class LibertyCellBlock:
    """Location of a parsed Liberty cell block.

    Attributes
    ----------
    name : str
        Liberty cell name from the ``cell (...)`` group.
    start : int
        Character offset where the cell block begins.
    end : int
        Character offset immediately after the cell block closes.
    """

    name: str
    start: int
    end: int


class LibertyHandler:
    """Modify Liberty text according to PDK input configuration.

    Parameters
    ----------
    config : PdkInputConfig
        Configuration containing optional Liberty cell additions, removals, and
        area overrides.
    """

    def __init__(
        self,
        config: PdkInputConfig,
    ) -> None:
        self.config = config

    def modify_liberty(self, liberty_text: str) -> str:
        """Return Liberty text with configured cell edits applied.

        Parameters
        ----------
        liberty_text : str
            Original Liberty library text.

        Returns
        -------
        str
            Liberty text after configured removals, area changes, and additions.
        """
        liberty_text = self._remove_cells(liberty_text)
        liberty_text = self._change_cell_areas(liberty_text)
        return self._add_cells(liberty_text)

    def _remove_cells(self, liberty_text: str) -> str:
        """Remove configured Liberty cell blocks.

        Parameters
        ----------
        liberty_text : str
            Liberty library text to modify.

        Returns
        -------
        str
            Liberty text with configured cells removed.

        Raises
        ------
        ValueError
            If any configured removal cell is not present.
        """
        cell_names = self.config.remove_liberty_cells or []
        if not cell_names:
            return liberty_text

        blocks_by_name = self._cell_blocks_by_name(liberty_text)
        missing_names = [name for name in cell_names if name not in blocks_by_name]
        if missing_names:
            raise ValueError(
                f"Could not remove missing Liberty cell(s): {', '.join(missing_names)}"
            )

        remove_ranges = sorted(
            (blocks_by_name[name].start, blocks_by_name[name].end)
            for name in cell_names
        )

        result_parts: list[str] = []
        cursor = 0
        for start, end in remove_ranges:
            result_parts.append(liberty_text[cursor:start])
            cursor = self._consume_trailing_blank_line(liberty_text, end)
        result_parts.append(liberty_text[cursor:])
        return "".join(result_parts)

    def _change_cell_areas(self, liberty_text: str) -> str:
        """Apply configured direct cell area overrides.

        Parameters
        ----------
        liberty_text : str
            Liberty library text to modify.

        Returns
        -------
        str
            Liberty text with configured area values replaced.

        Raises
        ------
        ValueError
            If a configured cell or its direct ``area`` attribute is missing.
        """
        area_changes = self.config.change_liberty_cell_area or {}
        if not area_changes:
            return liberty_text

        blocks_by_name = self._cell_blocks_by_name(liberty_text)
        missing_names = [name for name in area_changes if name not in blocks_by_name]
        if missing_names:
            raise ValueError(
                "Could not change area for missing Liberty cell(s): "
                f"{', '.join(missing_names)}"
            )

        replacements: list[tuple[int, int, str]] = []
        for name, area in area_changes.items():
            block = blocks_by_name[name]
            area_match = self._find_direct_cell_area(liberty_text, block)
            if area_match is None:
                raise ValueError(f"Could not find area for Liberty cell: {name}")
            line_start, value_start, value_end = area_match
            area_prefix = liberty_text[line_start:value_start]
            replacements.append(
                (
                    line_start,
                    value_end,
                    f"{area_prefix}{area:g}",
                )
            )

        return self._apply_replacements(liberty_text, replacements)

    def _add_cells(self, liberty_text: str) -> str:
        """Append configured Liberty cell fragments to the library.

        Parameters
        ----------
        liberty_text : str
            Liberty library text to modify.

        Returns
        -------
        str
            Liberty text with configured cell blocks inserted before the
            library closing brace.

        Raises
        ------
        ValueError
            If an added fragment is empty, malformed, or duplicates an existing
            cell name.
        """
        cell_fragments = self.config.add_liberty_cells or []
        if not cell_fragments:
            return liberty_text

        existing_names = set(self._cell_blocks_by_name(liberty_text))
        added_names: set[str] = set()
        added_blocks: list[str] = []

        for fragment in cell_fragments:
            fragment_blocks = self._extract_add_cell_blocks(fragment)
            if not fragment_blocks:
                raise ValueError("Liberty cell fragment does not contain any cells")

            for block in fragment_blocks:
                if block.name in existing_names:
                    raise ValueError(
                        "Could not add duplicate Liberty cell already in library: "
                        f"{block.name}"
                    )
                if block.name in added_names:
                    raise ValueError(
                        "Could not add duplicate Liberty cell in fragments: "
                        f"{block.name}"
                    )
                added_names.add(block.name)
                added_blocks.append(fragment[block.start : block.end].strip())

        library_close = self._find_library_close(liberty_text)
        cells_text = "\n\n".join(
            self._indent_cell_block(block) for block in added_blocks
        )
        insertion = f"\n\n{cells_text}\n"
        return liberty_text[:library_close] + insertion + liberty_text[library_close:]

    def _extract_add_cell_blocks(self, fragment: str) -> list[LibertyCellBlock]:
        """Extract cell blocks from an added Liberty fragment.

        Parameters
        ----------
        fragment : str
            Liberty fragment containing one or more complete ``cell`` blocks.

        Returns
        -------
        list[LibertyCellBlock]
            Parsed cell block locations within ``fragment``.

        Raises
        ------
        ValueError
            If the fragment contains meaningful non-comment text outside cell
            blocks.
        """
        blocks = list(self._iter_cell_blocks(fragment))
        covered_ranges = [(block.start, block.end) for block in blocks]
        non_cell_text = self._remove_ranges(fragment, covered_ranges)
        if self._has_meaningful_text(non_cell_text):
            raise ValueError("Liberty cell fragment contains text outside cell blocks")
        return blocks

    def _cell_blocks_by_name(self, liberty_text: str) -> dict[str, LibertyCellBlock]:
        """Return parsed cell blocks keyed by cell name.

        Parameters
        ----------
        liberty_text : str
            Liberty text to scan.

        Returns
        -------
        dict[str, LibertyCellBlock]
            Mapping from Liberty cell names to their block locations.

        Raises
        ------
        ValueError
            If duplicate cell names are found in the Liberty text.
        """
        blocks_by_name: dict[str, LibertyCellBlock] = {}
        for block in self._iter_cell_blocks(liberty_text):
            if block.name in blocks_by_name:
                raise ValueError(f"Duplicate Liberty cell found: {block.name}")
            blocks_by_name[block.name] = block
        return blocks_by_name

    def _iter_cell_blocks(self, liberty_text: str) -> list[LibertyCellBlock]:
        """Parse Liberty cell blocks from text.

        Parameters
        ----------
        liberty_text : str
            Liberty text or fragment to scan.

        Returns
        -------
        list[LibertyCellBlock]
            Cell block locations in the order they appear.

        Raises
        ------
        ValueError
            If a discovered ``cell`` group is malformed or has unmatched braces.
        """
        blocks: list[LibertyCellBlock] = []
        i = 0
        while i < len(liberty_text):
            group_start = self._find_group_start(liberty_text, "cell", i)
            if group_start is None:
                break

            open_paren = self._skip_whitespace(
                liberty_text,
                group_start + len("cell"),
            )
            close_paren = self._find_matching_paren(liberty_text, open_paren)
            name = liberty_text[open_paren + 1 : close_paren].strip()
            name = self._unquote_name(name)
            open_brace = self._skip_whitespace(liberty_text, close_paren + 1)
            if open_brace >= len(liberty_text) or liberty_text[open_brace] != "{":
                raise ValueError(f"Malformed Liberty cell group: {name}")
            close_brace = self._find_matching_brace(liberty_text, open_brace)
            blocks.append(
                LibertyCellBlock(
                    name=name,
                    start=group_start,
                    end=close_brace + 1,
                )
            )
            i = close_brace + 1
        return blocks

    def _find_direct_cell_area(
        self,
        liberty_text: str,
        block: LibertyCellBlock,
    ) -> tuple[int, int, int] | None:
        """Find the direct ``area`` attribute inside a cell block.

        Parameters
        ----------
        liberty_text : str
            Liberty text containing ``block``.
        block : LibertyCellBlock
            Cell block to inspect.

        Returns
        -------
        tuple[int, int, int] | None
            Tuple of line start, area value start, and area value end offsets, or
            ``None`` when no direct area attribute exists.
        """
        open_brace = liberty_text.find("{", block.start, block.end)
        if open_brace == -1:
            return None

        i = open_brace + 1
        depth = 0
        in_string = False
        in_line_comment = False
        in_block_comment = False
        while i < block.end - 1:
            char = liberty_text[i]
            next_char = liberty_text[i + 1] if i + 1 < block.end else ""

            if in_line_comment:
                in_line_comment = char != "\n"
                i += 1
                continue
            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                    i += 2
                else:
                    i += 1
                continue
            if in_string:
                if char == "\\":
                    i += 2
                    continue
                if char == '"':
                    in_string = False
                i += 1
                continue
            if char == "/" and next_char == "/":
                in_line_comment = True
                i += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                i += 2
                continue
            if char == '"':
                in_string = True
                i += 1
                continue
            if char == "{":
                depth += 1
                i += 1
                continue
            if char == "}":
                depth -= 1
                i += 1
                continue

            if depth == 0 and self._starts_identifier(liberty_text, i, "area"):
                colon = self._skip_whitespace(liberty_text, i + len("area"))
                if colon < block.end and liberty_text[colon] == ":":
                    value_start = self._skip_whitespace(liberty_text, colon + 1)
                    semicolon = self._find_semicolon(
                        liberty_text,
                        value_start,
                        block.end,
                    )
                    line_start = liberty_text.rfind("\n", block.start, i) + 1
                    return line_start, value_start, semicolon
            i += 1

        return None

    def _find_library_close(self, liberty_text: str) -> int:
        """Find the closing brace of the top-level Liberty library group.

        Parameters
        ----------
        liberty_text : str
            Complete Liberty library text.

        Returns
        -------
        int
            Character offset of the library closing brace.

        Raises
        ------
        ValueError
            If the library group is missing or malformed.
        """
        library_start = self._find_group_start(liberty_text, "library", 0)
        if library_start is None:
            raise ValueError("Could not find Liberty library group")
        open_paren = self._skip_whitespace(
            liberty_text,
            library_start + len("library"),
        )
        close_paren = self._find_matching_paren(liberty_text, open_paren)
        open_brace = self._skip_whitespace(liberty_text, close_paren + 1)
        if open_brace >= len(liberty_text) or liberty_text[open_brace] != "{":
            raise ValueError("Malformed Liberty library group")
        return self._find_matching_brace(liberty_text, open_brace)

    def _find_group_start(
        self,
        liberty_text: str,
        group_name: str,
        start: int,
    ) -> int | None:
        """Find the next Liberty group start outside strings and comments.

        Parameters
        ----------
        liberty_text : str
            Liberty text to scan.
        group_name : str
            Group identifier to find, such as ``"cell"`` or ``"library"``.
        start : int
            Character offset where scanning begins.

        Returns
        -------
        int | None
            Start offset of the matching group, or ``None`` when no match is
            found.
        """
        i = start
        in_string = False
        in_line_comment = False
        in_block_comment = False
        while i < len(liberty_text):
            char = liberty_text[i]
            next_char = liberty_text[i + 1] if i + 1 < len(liberty_text) else ""

            if in_line_comment:
                in_line_comment = char != "\n"
                i += 1
                continue
            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                    i += 2
                else:
                    i += 1
                continue
            if in_string:
                if char == "\\":
                    i += 2
                    continue
                if char == '"':
                    in_string = False
                i += 1
                continue
            if char == "/" and next_char == "/":
                in_line_comment = True
                i += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                i += 2
                continue
            if char == '"':
                in_string = True
                i += 1
                continue

            if self._starts_identifier(liberty_text, i, group_name):
                open_paren = self._skip_whitespace(
                    liberty_text,
                    i + len(group_name),
                )
                if open_paren < len(liberty_text) and liberty_text[open_paren] == "(":
                    return i
            i += 1

        return None

    def _find_matching_brace(self, liberty_text: str, open_brace: int) -> int:
        """Find the closing brace matching an opening brace.

        Parameters
        ----------
        liberty_text : str
            Text containing the opening brace.
        open_brace : int
            Character offset of the opening brace.

        Returns
        -------
        int
            Character offset of the matching closing brace.
        """
        return self._find_matching_delimiter(liberty_text, open_brace, "{", "}")

    def _find_matching_paren(self, liberty_text: str, open_paren: int) -> int:
        """Find the closing parenthesis matching an opening parenthesis.

        Parameters
        ----------
        liberty_text : str
            Text containing the opening parenthesis.
        open_paren : int
            Character offset of the opening parenthesis.

        Returns
        -------
        int
            Character offset of the matching closing parenthesis.
        """
        return self._find_matching_delimiter(liberty_text, open_paren, "(", ")")

    def _find_matching_delimiter(
        self,
        liberty_text: str,
        open_index: int,
        open_char: str,
        close_char: str,
    ) -> int:
        """Find a matching delimiter while ignoring strings and comments.

        Parameters
        ----------
        liberty_text : str
            Text containing the opening delimiter.
        open_index : int
            Character offset of the opening delimiter.
        open_char : str
            Opening delimiter character.
        close_char : str
            Closing delimiter character.

        Returns
        -------
        int
            Character offset of the matching closing delimiter.

        Raises
        ------
        ValueError
            If the opening delimiter is invalid or no match exists.
        """
        if open_index >= len(liberty_text) or liberty_text[open_index] != open_char:
            raise ValueError(f"Expected '{open_char}' in Liberty text")

        depth = 0
        i = open_index
        in_string = False
        in_line_comment = False
        in_block_comment = False
        while i < len(liberty_text):
            char = liberty_text[i]
            next_char = liberty_text[i + 1] if i + 1 < len(liberty_text) else ""

            if in_line_comment:
                in_line_comment = char != "\n"
                i += 1
                continue
            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                    i += 2
                else:
                    i += 1
                continue
            if in_string:
                if char == "\\":
                    i += 2
                    continue
                if char == '"':
                    in_string = False
                i += 1
                continue
            if char == "/" and next_char == "/":
                in_line_comment = True
                i += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                i += 2
                continue
            if char == '"':
                in_string = True
                i += 1
                continue
            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    return i
            i += 1

        raise ValueError(f"Unmatched '{open_char}' in Liberty text")

    def _find_semicolon(self, liberty_text: str, start: int, end: int) -> int:
        """Find the next semicolon outside quoted strings.

        Parameters
        ----------
        liberty_text : str
            Text to scan.
        start : int
            Character offset where scanning begins.
        end : int
            Character offset where scanning stops.

        Returns
        -------
        int
            Character offset of the semicolon.

        Raises
        ------
        ValueError
            If no semicolon is found before ``end``.
        """
        i = start
        in_string = False
        while i < end:
            char = liberty_text[i]
            if in_string:
                if char == "\\":
                    i += 2
                    continue
                if char == '"':
                    in_string = False
                i += 1
                continue
            if char == '"':
                in_string = True
                i += 1
                continue
            if char == ";":
                return i
            i += 1
        raise ValueError("Missing semicolon in Liberty area attribute")

    def _skip_whitespace(self, liberty_text: str, start: int) -> int:
        """Skip whitespace from a starting offset.

        Parameters
        ----------
        liberty_text : str
            Text to scan.
        start : int
            Character offset where scanning begins.

        Returns
        -------
        int
            First offset at or after ``start`` that is not whitespace.
        """
        i = start
        while i < len(liberty_text) and liberty_text[i].isspace():
            i += 1
        return i

    def _starts_identifier(self, text: str, index: int, identifier: str) -> bool:
        """Return whether text starts with a whole identifier at an offset.

        Parameters
        ----------
        text : str
            Text to inspect.
        index : int
            Candidate start offset.
        identifier : str
            Identifier to match.

        Returns
        -------
        bool
            ``True`` when ``identifier`` appears at ``index`` with identifier
            boundaries on both sides.
        """
        if not text.startswith(identifier, index):
            return False
        before = text[index - 1] if index > 0 else ""
        after_index = index + len(identifier)
        after = text[after_index] if after_index < len(text) else ""
        return not self._is_identifier_char(before) and not self._is_identifier_char(
            after
        )

    def _is_identifier_char(self, char: str) -> bool:
        """Return whether a character is part of a Liberty identifier.

        Parameters
        ----------
        char : str
            Character to classify.

        Returns
        -------
        bool
            ``True`` for alphanumeric characters and common Liberty identifier
            punctuation.
        """
        return bool(char) and (char.isalnum() or char in "_-.")

    def _unquote_name(self, name: str) -> str:
        """Remove surrounding double quotes from a Liberty name.

        Parameters
        ----------
        name : str
            Liberty group name text.

        Returns
        -------
        str
            Name without one pair of surrounding double quotes, when present.
        """
        if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
            return name[1:-1]
        return name

    def _consume_trailing_blank_line(self, text: str, start: int) -> int:
        """Consume whitespace and one trailing newline after a removed block.

        Parameters
        ----------
        text : str
            Text containing the removed range.
        start : int
            Character offset immediately after the removed block.

        Returns
        -------
        int
            Updated offset after optional trailing whitespace and newline.
        """
        match = re.match(r"[ \t]*(?:\r?\n)?", text[start:])
        if match is None:
            return start
        return start + match.end()

    def _remove_ranges(self, text: str, ranges: list[tuple[int, int]]) -> str:
        """Return text with ranges removed.

        Parameters
        ----------
        text : str
            Text to slice.
        ranges : list[tuple[int, int]]
            Start and end offsets to remove.

        Returns
        -------
        str
            Text with all ranges removed.
        """
        parts: list[str] = []
        cursor = 0
        for start, end in sorted(ranges):
            parts.append(text[cursor:start])
            cursor = end
        parts.append(text[cursor:])
        return "".join(parts)

    def _has_meaningful_text(self, text: str) -> bool:
        """Return whether text contains non-comment, non-whitespace content.

        Parameters
        ----------
        text : str
            Text to inspect.

        Returns
        -------
        bool
            ``True`` when any meaningful text remains after ignoring whitespace
            and C-style comments.
        """
        i = 0
        in_line_comment = False
        in_block_comment = False
        while i < len(text):
            char = text[i]
            next_char = text[i + 1] if i + 1 < len(text) else ""

            if in_line_comment:
                in_line_comment = char != "\n"
                i += 1
                continue
            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                    i += 2
                else:
                    i += 1
                continue
            if char == "/" and next_char == "/":
                in_line_comment = True
                i += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                i += 2
                continue
            if not char.isspace():
                return True
            i += 1

        return False

    def _apply_replacements(
        self,
        text: str,
        replacements: list[tuple[int, int, str]],
    ) -> str:
        """Apply non-overlapping text replacements.

        Parameters
        ----------
        text : str
            Original text.
        replacements : list[tuple[int, int, str]]
            Replacement tuples containing start offset, end offset, and
            replacement text.

        Returns
        -------
        str
            Text after applying replacements in offset order.
        """
        parts: list[str] = []
        cursor = 0
        for start, end, replacement in sorted(replacements):
            parts.append(text[cursor:start])
            parts.append(replacement)
            cursor = end
        parts.append(text[cursor:])
        return "".join(parts)

    def _indent_cell_block(self, cell_block: str) -> str:
        """Normalize an added cell block to library indentation.

        Parameters
        ----------
        cell_block : str
            Complete Liberty cell block.

        Returns
        -------
        str
            Cell block dedented to its minimum indentation and reindented by two
            spaces.
        """
        lines = cell_block.splitlines()
        if not lines:
            return cell_block

        non_empty_lines = [line for line in lines if line.strip()]
        min_indent = min(len(line) - len(line.lstrip()) for line in non_empty_lines)
        dedented_lines = [line[min_indent:] if line.strip() else "" for line in lines]
        return "\n".join(f"  {line}" if line else line for line in dedented_lines)
