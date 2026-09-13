"""The command that turns a speaker proposal into a record.

`convener-handle-proposal` is the only entry point in this package a
member of the public can reach, through the form relay, and
`convener_ops.journey.proposal` is where every decision about the payload
is made -- this opens `speakers.yml` and writes the result back.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

from convener_ops.cli import store
from convener_ops.declaration.paths import (
    DATA_DIR,
    repo_root,
)
from convener_ops.governance.rule import paris_today
from convener_ops.journey.proposal import (
    field_value,
    skip_reason,
    to_lead,
    verify_signature,
)


def handle_proposal() -> int:
    """Turn a signed Tally webhook into a lead, or refuse it.

    ``PROPOSAL_PAYLOAD`` is the raw body Tally signed -- not a wrapper
    around it -- so verifying the signature against it and then parsing it
    as JSON are both operating on exactly what Tally sent. The workflow
    (.github/workflows/candidate-form.yml) sets it from
    ``client_payload.body``, which the relay (services/form-relay) sends
    separately from ``client_payload.signature`` for exactly this reason: a
    signature cannot verify a payload that contains that signature.
    """
    payload_str = os.environ.get("PROPOSAL_PAYLOAD", "")
    signature = os.environ.get("PROPOSAL_SIGNATURE", "").strip()
    secret = os.environ.get("TALLY_WEBHOOK_SECRET", "").strip()

    if not payload_str:
        print("no payload", file=sys.stderr)
        return 1

    if not verify_signature(payload_str, signature, secret):
        print("invalid signature", file=sys.stderr)
        return 1

    # `payload_str` is signature-checked above, never schema-checked: a
    # signature only proves who sent the body, not that it parses as JSON
    # or that it is a JSON object rather than, say, an array. With no
    # secret configured, verify_signature accepts anything (D-13), which
    # makes this reachable in production, not just a defensive guess.
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        print("invalid JSON payload", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("invalid JSON payload", file=sys.stderr)
        return 1

    fields_list = (
        payload.get("data", {}).get("fields")
        if isinstance(payload.get("data"), dict)
        else payload.get("fields")
    )
    if not isinstance(fields_list, list):
        fields_list = []
    # field_value resolves a picker's chosen option id(s) against that
    # field's own `options` array -- without it, a DROPDOWN/
    # MULTIPLE_CHOICE/CHECKBOXES/MULTI_SELECT answer's raw `value` is a list
    # of ids, never the text `to_lead` compares against `GENDERS`/
    # `CAREER_STAGES`, and every such answer would silently become
    # "undisclosed". This is the one place in the repository that flattens
    # a Tally field into `to_lead`'s `fields: dict[str, str]`.
    fields = {
        f.get("label", ""): field_value(f) for f in fields_list if isinstance(f, dict)
    }

    root = repo_root()
    speakers_path = root / DATA_DIR / "speakers.yml"
    speakers, errors = store.load(speakers_path)
    cfg, cfg_errors = store.load(root / DATA_DIR / "config.yml")
    if errors or cfg_errors:
        for error in errors + cfg_errors:
            print(f"  - {error}")
        return 1
    speakers = speakers or []

    # The Paris day, not the UTC one: this date seeds the vote window
    # (`selection.opened_on`), so a submission arriving between 00:00 and 02:00
    # Paris would otherwise open a window dated a day early and every deadline
    # derived from it would inherit the error.
    today = paris_today(datetime.now(UTC)).isoformat()
    lead = to_lead(fields, speakers, cfg or {}, today)
    if lead is None:
        print(f"skipping: {skip_reason(fields, speakers)}")
        return 0

    speakers.append(lead)
    speakers_path.write_text(
        # Under the header the file already had. `dump_speakers` substitutes a
        # constant, which is right for a file being created and wrong for one
        # being edited -- see `store.under_its_own_header`.
        store.speakers_under_own_header(
            speakers_path.read_text(encoding="utf-8"), speakers
        ),
        encoding="utf-8",
        newline="",
    )
    print(f"created {lead['id']} from form proposal")
    return 0
