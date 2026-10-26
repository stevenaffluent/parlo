"""Turning raw transcripts into the text we insert: tidy-up, word replacements, spoken note commands."""
import re

from engine import tidy


def postprocess(text, settings):
    if settings["tidy"]:
        text = tidy(text)
    for line in settings["replacements"].splitlines():
        if "=>" not in line:
            continue
        heard, wanted = (p.strip() for p in line.split("=>", 1))
        if heard:
            wanted = wanted.replace("\\n", "\n")
            # a spoken command like "new line" also swallows the comma/period the model put after it
            tail = r"[,.]?" if not wanted.strip() else ""
            text = re.sub(r"(?i)(?<!\w)" + re.escape(heard) + r"(?!\w)" + tail, lambda m: wanted, text)
    text = re.sub(r" *\n *", "\n", text).strip(" ")
    if settings["trailing_space"] and text and not text.endswith(("\n", " ")):
        text += " "
    return text


# Spoken formatting for Notes. Each phrase becomes a structural token the editor applies.
NOTE_COMMANDS = {
    "new paragraph": "para", "next paragraph": "para",
    "new line": "line", "next line": "line",
    "bullet point": "bullet", "new bullet": "bullet", "next bullet": "bullet",
    "numbered point": "number", "next number": "number", "number point": "number",
    "new heading": "heading",
    "end list": "endlist", "stop list": "endlist",
}
# A command only counts at the start or right after punctuation (where the speaker paused), so
# "the new line of products" stays text while "...products. New line." is a command.
_CMD_RE = re.compile(r"(?:^|(?<=[.,;:!?]))\s*\b(" + "|".join(sorted(map(re.escape, NOTE_COMMANDS), key=len, reverse=True))
                     + r")\b[,.;:]?\s*", re.I)


def note_tokens(text):
    """'Shopping. Bullet point milk. Bullet point eggs. New paragraph. Thanks.' ->
    [text 'Shopping.', bullet, text 'Milk', bullet, text 'Eggs', para, text 'Thanks.']
    Paragraphs keep their punctuation; list items and headings lose the trailing full stop/comma."""
    parts = _CMD_RE.split(text.strip())
    tokens, after_cmd, context = [], False, "para"
    for i, part in enumerate(parts):
        if i % 2:
            kind = NOTE_COMMANDS[part.lower()]
            tokens.append({"t": kind})
            context = "para" if kind in ("para", "endlist", "line") else kind
            after_cmd = True
            continue
        part = part.strip()
        if context != "para":
            part = part.rstrip(",.;:").strip()
        if not part:
            continue
        if after_cmd:
            part = part[0].upper() + part[1:]
        tokens.append({"t": "text", "v": part})
        after_cmd = False
    return tokens
