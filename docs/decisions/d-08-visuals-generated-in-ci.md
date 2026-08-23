# D-08 — Announcement visuals are generated, not hand-drawn

**Status:** Accepted

## Context

Producing the announcement image and flyer by hand in a design tool meant
inserting the registration QR code manually each time — forgotten at least
once, requiring the flyer to be redone — and titles that overran their box
instead of wrapping to fit it.

## Decision

The announcement visual and flyer are generated from an event's own data:
rendered as HTML/CSS to an image, not produced by hand in a design tool.

This is feasible because everything that makes the organisation's visual
identity recognisable — banding, motifs, typography — is fixed; only the
title, date, photo, speaker name and affiliation, and QR code vary per
event. Colour and type values are read from the single shared brand source
([D-16](d-16-brand-source-of-truth.md)), the same file every other
implementation of the identity reads.

## Rejected

Continuing to produce visuals by hand for every event.

## Cost

Whoever prefers to work in a design tool still can: the templates are kept
as downloadable assets in the repository, with a direct link from the
handbook. Opening one in a personal copy of any design tool needs no shared
account. In exchange for automatic QR codes and titles that fit, the
templates themselves become code that has to stay in step with the brand
source rather than artwork a designer can freely restyle.
