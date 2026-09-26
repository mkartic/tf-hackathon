"""Scrub: remove secrets and personal data from a skill proposal before anyone sees it.

Deterministic (regexes plus a Shannon-entropy check for unlabelled tokens) and stdlib-only,
so the same file runs in skillsmith and, as a standalone script, in a TrueForge sandbox:

    python scrub.py SKILL.md scripts/x.py     # JSON report: scrubbed files + findings
    python scrub.py --write SKILL.md          # scrub the files in place, report on stderr
    python scrub.py < draft.md                # scrubbed text on stdout, findings on stderr

Each removed value is replaced with a `[scrubbed:<kind>]` marker. Markers already present
(say, from a scrub in the sandbox) are reported again, so the PR still says what was removed.
Findings never contain the removed value.
"""

import json
import math
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass

SECRET = "secret"
PERSONAL = "personal data"

MARKER = re.compile(r"\[scrubbed:([a-z0-9-]+)\]")


@dataclass(frozen=True)
class Finding:
    kind: str
    category: str
    line: int
    file: str | None = None
    earlier: bool = False  # the marker was already there when skillsmith saw it

    def where(self) -> str:
        return f"`{self.file}` line {self.line}" if self.file else f"line {self.line}"


@dataclass(frozen=True)
class _Rule:
    kind: str
    category: str
    pattern: re.Pattern
    group: int = 0  # the part of the match to remove
    check: object = None  # optional predicate on the removed value


def _luhn(digits: str) -> bool:
    nums = [int(d) for d in re.sub(r"\D", "", digits)][::-1]
    total = sum(n if i % 2 == 0 else (n * 2 - 9 if n > 4 else n * 2) for i, n in enumerate(nums))
    return 13 <= len(nums) <= 19 and total % 10 == 0


PLACEHOLDER = re.compile(
    r"""^(?:
        [$%<{].*                     # $VAR, ${VAR}, %VAR%, <token>, {token}
      | (?-i:[A-Z][A-Z0-9_]*)        # an env var name
      | (?:os\.)?(?:environ|getenv).*
      | [A-Za-z_][\w.]*\(.*          # a function call: code, not a value
      | (?:x+|\*+|\.+|-+|0+)         # xxxx, ****, ...
      | (?:your|my|example|dummy|fake|test|changeme|placeholder|redacted|none|null|true|false)\b.*
      | \[scrubbed:.*
    )$""",
    re.I | re.X,
)

EXAMPLE_EMAIL_DOMAINS = re.compile(r"@(?:[\w-]+\.)*example\.(?:com|org|net)$|noreply", re.I)


def _not_placeholder(value: str) -> bool:
    return not PLACEHOLDER.match(value.strip("'\""))


def _public_ipv4(value: str) -> bool:
    octets = [int(o) for o in value.split(".")]
    return (
        all(o <= 255 for o in octets)
        and octets[0] not in (0, 10, 127)
        and octets[:2] != [192, 168]
        and not (octets[0] == 172 and 16 <= octets[1] <= 31)
        and octets[:3] != [192, 0, 2]  # documentation range
    )


# Order matters only for ties: at one position the longest match wins, then the earliest rule.
RULES = [
    _Rule("private-key", SECRET, re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)),
    _Rule("aws-access-key", SECRET, re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    _Rule("github-token", SECRET, re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    _Rule("api-key", SECRET, re.compile(r"\bsk-(?:proj-|ant-|live-)?[A-Za-z0-9_-]{20,}")),
    _Rule("api-key", SECRET, re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    _Rule("api-key", SECRET, re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    _Rule("slack-token", SECRET, re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    _Rule("jwt", SECRET, re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    _Rule("bearer-token", SECRET, re.compile(
        r"\b(?:Bearer|Token)\s+([A-Za-z0-9._~+/-]{16,}=*)"), group=1, check=_not_placeholder),
    _Rule("url-password", SECRET, re.compile(
        r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s@/]+)@"), group=1, check=_not_placeholder),
    _Rule("credential", SECRET, re.compile(
        r"""(?ix)
        \b[\w.-]*(?:api[_-]?key|secret|token|passw(?:or)?d|pwd|access[_-]?key|auth[_-]?key)
        ["']?\s*[:=]\s*
        ( "[^"\n]{8,}" | '[^'\n]{8,}' | [^\s"'`,;)}\]]{8,} )
        """), group=1, check=_not_placeholder),
    _Rule("email", PERSONAL, re.compile(
        r"(?<![:/\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b"),
          check=lambda v: not EXAMPLE_EMAIL_DOMAINS.search(v)),
    _Rule("phone", PERSONAL, re.compile(
        r"(?<![\w.:/-])\+?\d{1,3}[ -]?\(?\d{2,4}\)?[ -]\d{3,4}[ -]\d{3,4}(?![\w.:/-])")),
    _Rule("card-number", PERSONAL, re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), check=_luhn),
    _Rule("ip-address", PERSONAL, re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
          check=_public_ipv4),
]

TOKEN = re.compile(r"(?<![A-Za-z0-9_+/-])[A-Za-z0-9_+/-]{24,}={0,2}(?![A-Za-z0-9_+/=-])")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEX = re.compile(r"^[0-9a-f]+$", re.I)
ENTROPY_BITS = 4.0  # per character; English words and identifiers sit well below


def shannon_entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def _looks_random(token: str) -> bool:
    if UUID.match(token) or HEX.match(token):  # ids and commit hashes, not secrets
        return False
    classes = sum(bool(re.search(p, token)) for p in (r"[a-z]", r"[A-Z]", r"\d"))
    return classes == 3 and shannon_entropy(token) >= ENTROPY_BITS


def _non_overlapping(spans, taken=()):
    """Earliest start wins, then the longest; ties keep list order. Skips `taken` ranges."""
    kept = list(taken)
    for span in sorted(spans, key=lambda s: (s[0], -(s[1] - s[0]))):
        if all(span[1] <= k[0] or span[0] >= k[1] for k in kept):
            kept.append(span)
    return sorted(kept)


def _spans(text: str) -> list[tuple[int, int, str, str]]:
    known = [(m.start(), m.end(), m[1], "marker") for m in MARKER.finditer(text)]
    for rule in RULES:
        for m in rule.pattern.finditer(text):
            start, end = m.span(rule.group)
            if start == end or (rule.check and not rule.check(m[rule.group])):
                continue
            known.append((start, end, rule.kind, rule.category))
    known = _non_overlapping(known)
    # Unlabelled random-looking strings, only where no specific rule already matched.
    unlabelled = [(m.start(), m.end(), "high-entropy-string", SECRET)
                  for m in TOKEN.finditer(text) if _looks_random(m[0])]
    return _non_overlapping(unlabelled, known)


def _category_of(kind: str) -> str:
    return next((r.category for r in RULES if r.kind == kind), SECRET)


def scrub_text(text: str, file: str | None = None) -> tuple[str, list[Finding]]:
    """The text with secrets and personal data replaced by markers, and what was removed."""
    findings, out, pos = [], [], 0
    for start, end, kind, category in _spans(text):
        line = text.count("\n", 0, start) + 1
        if category == "marker":
            findings.append(Finding(kind, _category_of(kind), line, file, earlier=True))
            continue
        findings.append(Finding(kind, category, line, file))
        out += [text[pos:start], f"[scrubbed:{kind}]"]
        pos = end
    out.append(text[pos:])
    return "".join(out), findings


def scrub_files(files: dict[str, str]) -> tuple[dict[str, str], list[Finding]]:
    scrubbed, findings = {}, []
    for path, content in files.items():
        scrubbed[path], found = scrub_text(content, path)
        findings += found
    return scrubbed, findings


def summary(findings: list[Finding]) -> str:
    """E.g. '2 possible secrets and 1 piece of personal data removed'."""
    secrets = sum(f.category == SECRET for f in findings)
    personal = len(findings) - secrets
    parts = []
    if secrets:
        parts.append(f"{secrets} possible secret{'s' if secrets != 1 else ''}")
    if personal:
        parts.append(f"{personal} piece{'s' if personal != 1 else ''} of personal data")
    return f"{' and '.join(parts)} removed" if parts else "No secrets or personal data found"


def report_markdown(findings: list[Finding]) -> str:
    lines = [summary(findings) + "."]
    for f in findings:
        note = " (scrubbed before drafting)" if f.earlier else ""
        lines.append(f"- {f.kind} ({f.category}) at {f.where()}{note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    write = "--write" in args
    paths = [a for a in args if a != "--write"]
    if not paths:
        text, findings = scrub_text(sys.stdin.read())
        sys.stdout.write(text)
        print(json.dumps([asdict(f) for f in findings]), file=sys.stderr)
        return 0
    originals = {}
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            originals[p] = fh.read()
    scrubbed, findings = scrub_files(originals)
    report = {"summary": summary(findings), "findings": [asdict(f) for f in findings]}
    if write:
        for p, content in scrubbed.items():
            if content != originals[p]:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(content)
        print(json.dumps(report, indent=2), file=sys.stderr)
    else:
        print(json.dumps(report | {"files": scrubbed}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
