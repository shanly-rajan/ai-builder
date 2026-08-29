# M12.3 Official-profile context and discovery integrity repair

Repair the live ScholarPath run in which every page extraction succeeded but no
Supervisor completed verification. Official person profiles returned exact identity,
affiliation, research, and availability sections, yet non-identity claims were downgraded
because each excerpt did not repeat the complete Supervisor name. The same run also exposed
malformed discovery institutions and unrecognized official person-profile URL layouts.

Implement only this bounded repair:

- Preserve exact excerpts and add an explicit evidence-to-identity provenance link for facts
  whose subject is established by a grounded identity claim on the same official person page.
- Permit that link only for official university profiles or institutional directories, the
  same Supervisor, the same source URL, an exact page identity, and independently valid typed
  claim fields. General pages, news, groups, and cross-source links remain ineligible.
- Support a conservative parenthesized given-name alias only when the page-stated alias and
  family name exactly match the discovered Supervisor.
- Reject generic, malformed, publisher, and role-bearing institution labels observed in the
  persisted run without inferring an affiliation from a hostname.
- Recognize singular official `persons`, `researcher`, `researchers`, and `directory` URL
  layouts while retaining HTTPS, exact identity, exact institution, academic-host, and source
  kind requirements.
- Keep identity, current institution and department, and research evidence mandatory. Keep
  availability separate, the five-Verified-Supervisor threshold unchanged, and exactly one
  alternate-source pass.

Add fixed offline regressions for same-page context links, aliases, first-person profile
sections, invalid cross-page or group-page context, malformed discovery labels, supported
official URL layouts, and retry exhaustion. Update the architecture, graph and prompt
versions, evaluation replay identifier, README, build journal, and repository contracts.
Run every quality gate and commit the repair separately. Do not call live providers.
