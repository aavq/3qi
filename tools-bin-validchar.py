#!/usr/bin/env python3

# import string
#
# ALLOWED_CHARS = set(
#     string.ascii_letters +  # A-Z, a-z
#     string.digits +         # 0-9
#     string.punctuation +    # !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~
#     ' \n\r\t'               # Пробелы и управляющие символы (табуляция, перевод строки)
# )

import argparse
from pathlib import Path
from typing import Set


def build_allowed_char_set() -> Set[str]:
    import string
    return set(
        string.ascii_letters +
        string.digits +
        string.punctuation +
        ' \n\r\t'
    )


def find_disallowed_characters(content: str, allowed_chars: Set[str]) -> Set[str]:
    return {ch for ch in content if ch not in allowed_chars}


def main():
    parser = argparse.ArgumentParser(description="Check for disallowed characters in a file.")
    parser.add_argument("file", type=Path, help="Path to the input text file.")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: File '{args.file}' does not exist.")
        return

    allowed_chars = build_allowed_char_set()
    content = args.file.read_text(encoding='utf-8', errors='replace')
    disallowed = find_disallowed_characters(content, allowed_chars)

    if not disallowed:
        print("All characters are allowed.")
        return

    print("Disallowed characters found:")
    for ch in sorted(disallowed):
        print(f"{repr(ch)} (U+{ord(ch):04X})")


if __name__ == "__main__":
    main()
