"""What this software calls itself when it calls somebody else's API.

Every outbound request this package makes goes through `urllib.request`,
and `urllib` sends `Python-urllib/3.x` as its User-Agent unless told
otherwise. That string is refused outright by Cloudflare's client-signature
filtering, which sits in front of more of the web than one would guess --
including both third-party APIs this project talks to.

Refused how: the request never reaches the origin. Cloudflare answers
`HTTP 403` with a body of `error code: 1010`, its own "access denied by
client signature", *before* the API sees the call. So the credential is
never evaluated, and the failure reads as an authentication problem that it
is not. `tools/scripts/create_tally_form.py` met exactly that against
`api.tally.so`, and spent an operator's attention on a key that was never
wrong.

**One header, stated here rather than at each call site**, because the
call sites fail at different times and a fix applied to one of them looks
complete. The Tally call runs while an instance is being stood up, so it
fails in front of whoever is standing it up; the two
`journey/platform_fcc.py` calls run only once an event exists, so the first
time they are exercised is the day of a webinar, with a room to open and a
recording to fetch. A shared decision cannot be half-applied; three
literals can.

**The relays already knew.** `services/form-relay` and
`services/signup-relay` each declare a `USER_AGENT` of their own and send
it on every `fetch`, beside a comment saying GitHub's REST API answers 403
without one. So this repository had learned the lesson and written it
down -- in JavaScript. Nothing carried it across the language boundary,
and the Python side was written as though the default were fine. The
relays keep their own names rather than this one, because
`convener-form-relay` and `convener-ops` are different software and an
honest name says which of them is calling; what they share is the rule,
and each language holds it in a test of its own --
`tools/tests/repository/test_outbound_user_agent.py` here, each relay's
own suite there.

Any honest value passes -- curl's own default does -- so this names the
software and its home and impersonates no browser. Impersonation would
also be the wrong answer to a filter that exists to tell automated clients
apart: this one says what it is.
"""

from __future__ import annotations

from typing import Final

#: Sent on every outbound request this package makes. `convener-ops` is
#: the distribution's own name in `tools/pyproject.toml`; the URL is what
#: lets an operator on the receiving end find out who called them.
USER_AGENT: Final = "convener-ops (+https://github.com/BenoitJT-GIRARD/convener)"
