"""Every console command `tools/pyproject.toml` declares, one module per
sub-package it dispatches into."""

from __future__ import annotations

from convener_ops.cli.declaration import (
    check_config,
)
from convener_ops.cli.governance import (
    alert_secret_workflow_run,
    notify_digest,
    notify_immediate,
    register,
    validate,
)
from convener_ops.cli.journey.attendance import (
    discard_recording,
    encrypt_attendance_export,
    match_attendance,
    release_recording,
)
from convener_ops.cli.journey.certificate import (
    certificates_public_data,
    deliver_certificate,
    deliver_certificates,
    issue_certificates,
    reissue_certificate,
    revoke_certificate,
)
from convener_ops.cli.journey.proposal import (
    handle_proposal,
)
from convener_ops.cli.journey.registration import (
    confirm_queued_registrations,
    drain_queue,
    encrypt_identifier,
    handle_registration,
    plan_queue_drain,
    registration_routing_public_data,
    resend_confirmation,
    resolve_registration_secret,
    send_confirmation,
)
from convener_ops.cli.journey.retention import (
    erase_registration,
    record_destructions,
    retention_sweep,
)
from convener_ops.cli.journey.survey import (
    invite_survey,
    record_survey_invitation,
)
from convener_ops.cli.maintenance import (
    actions_usage_window,
    check_actions_usage_liveness,
    check_credential_expiry,
    check_queue_liveness,
    check_registration_routing,
    check_retention_liveness,
    record_actions_usage,
    record_queue_watch,
    record_retention_run,
    sweep,
)
from convener_ops.cli.publication import (
    agenda_internal,
    public_data,
    render_announcements,
    render_poster_fixtures,
    render_template_fixtures,
    render_visual_fixtures,
    render_visuals,
    survey_status_public_data,
)

__all__ = [
    "actions_usage_window",
    "agenda_internal",
    "alert_secret_workflow_run",
    "certificates_public_data",
    "check_actions_usage_liveness",
    "check_config",
    "check_credential_expiry",
    "check_queue_liveness",
    "check_registration_routing",
    "check_retention_liveness",
    "confirm_queued_registrations",
    "deliver_certificate",
    "deliver_certificates",
    "discard_recording",
    "drain_queue",
    "encrypt_attendance_export",
    "encrypt_identifier",
    "erase_registration",
    "handle_proposal",
    "handle_registration",
    "invite_survey",
    "issue_certificates",
    "match_attendance",
    "notify_digest",
    "notify_immediate",
    "plan_queue_drain",
    "public_data",
    "record_actions_usage",
    "record_destructions",
    "record_queue_watch",
    "record_retention_run",
    "record_survey_invitation",
    "register",
    "registration_routing_public_data",
    "reissue_certificate",
    "release_recording",
    "render_announcements",
    "render_poster_fixtures",
    "render_template_fixtures",
    "render_visual_fixtures",
    "render_visuals",
    "resend_confirmation",
    "resolve_registration_secret",
    "retention_sweep",
    "revoke_certificate",
    "send_confirmation",
    "survey_status_public_data",
    "sweep",
    "validate",
]
