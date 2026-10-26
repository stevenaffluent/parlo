"""Turning raw transcripts into the text we insert: tidy-up, word replacements, spoken note commands."""
import re

from engine import tidy
from spell import is_word


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


# ---- personal dictionary ---------------------------------------------------------------
def dictionary_terms(settings):
    return [t.strip() for t in settings.get("dictionary", "").splitlines() if t.strip()]


def apply_dictionary(text, terms):
    """Fix near-misses of the user's own words: 'Paulo' -> 'Parlo', 'Open AI' -> 'OpenAI'.
    A span of words is replaced when it is spelt alike (similar letters, same first letter),
    so ordinary words are left alone."""
    from difflib import SequenceMatcher

    if not terms or not text:
        return text
    letters = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    words = re.findall(r"\S+", text)
    for term in sorted(terms, key=len, reverse=True):
        key = letters(term)
        if len(key) < 4:
            continue  # too short to fuzzy-match safely; exact case is still fixed below
        n_term = len(term.split())
        for n in sorted({n_term, n_term + 1, max(1, n_term - 1)}):
            i = 0
            while i + n <= len(words):
                chunk = words[i:i + n]
                cand = letters("".join(chunk))
                bare = re.sub(r"[^\w' ]+$", "", " ".join(chunk))
                slack = 1 if len(key) <= 6 else 2  # 'parlour' must not become 'Parlo'
                real_words = all(is_word(re.sub(r"[^A-Za-z]", "", w)) for w in chunk)
                # same letters, split into words ('Open AI' for 'OpenAI'), or a non-word in the wrong case
                same_letters = cand == key and bare != term and (len(chunk) > 1 or not real_words)
                if cand and bare != term and cand[0] == key[0] and abs(len(cand) - len(key)) <= slack \
                        and (same_letters or (not real_words and SequenceMatcher(None, cand, key).ratio() >= (0.72 if len(key) >= 8 else 0.8))):
                    tail = re.search(r"[^\w']*$", chunk[-1]).group(0)  # keep the punctuation after it
                    words[i:i + n] = [term + tail]
                i += 1
    text = " ".join(words)
    for term in terms:  # exact matches in the wrong case: 'openai' -> 'OpenAI'
        if term[:1].isupper() and term[1:] == term[1:].lower() and is_word(term):
            continue  # 'Notion' is also the word 'notion': only a real typo is corrected, not the word
        text = re.sub(r"(?i)(?<!\w)" + re.escape(term) + r"(?!\w)", term, text)
    return text


# ---- voice actions -------------------------------------------------------------------------
# Said on their own, these do something instead of being typed.
WHOLE_COMMANDS = {
    "undo that": "undo", "undo": "undo", "scratch that": "delete_last", "delete that": "delete_last",
    "select all": "select_all", "copy that": "copy", "press enter": "enter", "send it": "enter",
    "send": "enter", "press tab": "tab", "press escape": "escape",
}
# Said at the end of a dictation, these run after the text is typed.
TRAILING = {"press enter": "enter", "send it": "enter", "send message": "enter", "and send": "enter",
            "press tab": "tab"}
_TRAIL_RE = re.compile(r"[,.]?\s*\b(" + "|".join(map(re.escape, TRAILING)) + r")\b[.!]?\s*$", re.I)


def parse_actions(text):
    """-> (text_to_type, [actions]). 'Thanks, see you soon. Send it.' -> ('Thanks, see you soon.', ['enter'])."""
    plain = re.sub(r"[^\w\s]", "", text).strip().lower()
    if plain in WHOLE_COMMANDS:
        return "", [WHOLE_COMMANDS[plain]]
    m = _TRAIL_RE.search(text)
    if m:
        body = text[:m.start()].rstrip()
        if body and body[-1].isalnum():
            body += "."
        return body, [TRAILING[m.group(1).lower()]]
    return text, []
