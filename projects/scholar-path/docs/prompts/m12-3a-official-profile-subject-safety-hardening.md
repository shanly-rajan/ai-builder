# M12.3a Official-profile subject safety hardening

Adversarially review the uncommitted M12.3 repair and close only the remaining
subject-ownership and availability-language gaps before committing it.

- Permit contextual evidence only on a deterministic singular official person-profile URL.
  Support bounded person routes such as `profile`, `profiles`, `people`, `persons`,
  `directory`, `staff-directory`, `faculty`, `researcher`, `researchers`, and
  `staff/<person>` and `staff/<id>/<person>`. Preserve the exact common
  `about/our-people/<person>` layout, while rejecting bare collections and generic, news,
  article, publication, project, group, search, event, About, or contact pages.
- Prevent an official directory or profile from lending one person's affiliation, research,
  or availability statement to another person. Inspect both the exact excerpt and its nearest
  person heading in the retrieved page. A role line such as `Professor of Artificial
  Intelligence` is not a new person heading.
- Do not bind evidence by surname alone. Permit a parenthesized given-name alias only when it
  has a conservative morphological relationship to the complete given name and the surname is
  identical. Reject arbitrary parentheticals such as `(AI)` or `(University)`.
- Require every contextual identity reference to resolve to direct identity evidence from the
  same Supervisor, URL, source kind, and retrieval timestamp. An unresolved reference must not
  affect verification, availability, Research Fit, or independent review.
- Reject unsupported availability or application-interest language from Research Fit and
  independent-review prose. Availability remains a separately evidenced status.

Add fixed offline regressions for every positive and negative boundary, keep the evidence prompt
at v3 and graph at m12.3, preserve the one-pass alternate retry and five-Supervisor threshold,
run every quality gate, and make no live provider or external network call.
