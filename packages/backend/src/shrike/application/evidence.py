"""Bounded lexical checks, never eval/compile/import repository source."""

import io
import token
import tokenize
from decimal import Decimal, InvalidOperation


def lexical(text: str) -> list[tuple[int, str]]:
    if len(text.encode()) > 204800:
        return []
    try:
        return [
            (item.type, item.string)
            for item in tokenize.generate_tokens(io.StringIO(text).readline)
            if item.type in {token.NAME, token.OP, token.NUMBER}
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []


def zero_division(text: str) -> bool:
    parts = lexical(text)
    for index, part in enumerate(parts[:-1]):
        if part in {(token.OP, "/"), (token.OP, "//")} and parts[index + 1][0] == token.NUMBER:
            try:
                if Decimal(parts[index + 1][1]).is_zero():
                    return True
            except InvalidOperation:
                continue
    return False


def eval_input(text: str) -> bool:
    parts = lexical(text)
    pattern = [(token.NAME, "eval"), (token.OP, "("), (token.NAME, "input"), (token.OP, "(")]
    return any(parts[index : index + 4] == pattern for index in range(len(parts) - 3))
