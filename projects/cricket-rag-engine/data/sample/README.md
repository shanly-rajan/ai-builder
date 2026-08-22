# Sample corpus data card

## Dataset identity

| Field | Value |
|---|---|
| File | `data/sample/laws.txt` |
| Purpose | Small educational fixture for parser, retrieval, generation, and evaluation experiments |
| Size | 24 lines, 369 words, 2,016 bytes |
| SHA-256 | `7d9d6394a54b193ef0c9a6078f9f37331eabeadab96f63f62c02addf620c6edd` |
| Parsed output | 11 LangChain documents: four Law-header chunks and seven section chunks |
| Authority | Not authoritative; incomplete and not verified against a current official edition |

This file is the only corpus supported by the current project. Adding another file to
this directory does not make it part of the runtime: the indexer defaults explicitly
to `data/sample/laws.txt`.

## Included content

| Law | Sections in the file | Clause groups represented |
|---|---|---|
| 19 — Boundaries | 19.4, 19.5 | 19.4.1–19.4.2 and 19.5.1–19.5.2 |
| 28 — The fielder | 28.3 | 28.3.1–28.3.2 |
| 34 — Hit the ball twice | 34.1, 34.3 | 34.1.1 and 34.3.1 |
| 38 — Run out | 38.1, 38.3 | 38.1.1 and 38.3.1 |

The fixture does not include the rest of these Laws, any other Law, definitions,
appendices, umpire signals, boundary allowances, competition playing conditions, or
revision history. A question requiring omitted material is unsupported even if a
retrieved section appears related.

## Format and parsing contract

The parser recognizes:

- `LAW <number> <title>` headings;
- `<law>.<section> <title>` section headings; and
- the following `<law>.<section>.<clause>` text as part of that section document.

Each output document receives `law_number`, `law_title`, `section`, and a static
`source` label. The metadata does not currently include a source URL, edition,
effective date, license, checksum, or individual sub-clause identifier. Pinecone IDs
are ordinal (`law_chunk_0`, `law_chunk_1`, and so on), not content-stable identifiers.

## Provenance and redistribution status

The repository currently records no source URL, publisher document title, edition or
effective date, retrieval date, verbatim/adapted status, or license/permission basis
for `laws.txt`. The parser's `MCC Laws of Cricket` source label is an attribution label,
not proof of provenance, currency, endorsement, or redistribution permission.

Before treating the fixture as redistributable or authoritative, record and verify:

- the exact source URL and document title;
- publisher and edition/effective date;
- retrieval date;
- whether the text is verbatim, excerpted, or adapted;
- the applicable license or written permission; and
- a checksum for the verified source artifact.

Until then, use this fixture only as a limited learning sample and independently verify
any real-world ruling against an authorized, current source.

Downloaded working documents belong in `data/raw/`, and generated chunks or indexes
belong in `data/processed/` or `data/index/`. Those directories are intentionally
ignored and must not contain credentials, private data, or unapproved copyrighted
corpora.
