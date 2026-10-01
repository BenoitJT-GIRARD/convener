# D-28 — The architect owns the organisation; a Board member writes the repository

**Status:** Accepted

## Context

G-16 already commits this project to a shape: every account and secret
belongs to the organisation, no personal account is ever used, the
handover procedure is documented, and the role that sets a system like
this up is explicitly transferable (D-11 is the account-and-vault
mechanism behind that promise). None of that says what "transferable"
means in GitHub's own permission model. Without a mapping onto a real
organisation role and a real repository role, G-16 is an intention a
reader has to trust, not a setting anyone can check.

A security review found that this gap has a sharp edge. **The property that
nobody with only write access can exfiltrate a secret cannot be
closed on this repository's hosting tier**: environments, branch
protection, required reviewers and an effective `CODEOWNERS` are all
unavailable on a private repository at GitHub's Free tier, so nothing
mechanical stops a collaborator with `Write` from adding a step to a
workflow that reads a sensitive secret and dispatching it against their
own branch. `.github/workflows/secret-workflow-monitor.yml` detects that
in minutes; nothing prevents it. Who holds `Write`, and for how long, is
the one free control this project has left over that exposure.

## Decision

Two roles, mapped onto two different, real GitHub scopes — never people,
the same discipline D-24 already asks of every operator command:

- **Architect = organisation owner.** Can add and remove anyone, and
  change any repository setting, independently of any Board membership.
  This is an *organisation* role: it does not come from sitting on the
  Board, and sitting on the Board does not carry it.
- **Board member = repository `Write`, and nothing else.** Never `Admin`.
  This is the floor the cockpit actually needs: every write it makes —
  casting a ballot included — goes through the GitHub API under the
  signed-in person's own token, so a member who cannot genuinely write to
  the repository cannot use the tool the Board relies on.
- **Handover is manual and deliberate, exactly as G-16 provides for:**
  promote the successor to owner, verify the promotion took, then step
  down. No step is combined with another, and no step is skipped because
  the previous one looked like it worked.

**The bus factor.** One
owner means nobody can administer the organisation — add a collaborator,
rotate a secret, or even transfer ownership itself — if that single
account is ever lost. The ordinary recommendation is at least two owners:
a working one, and a second, "break glass" holder who never uses the role
day to day and exists only so the organisation survives the loss of the
first. That second seat is itself a trade, not a free improvement — see
Cost, below — so this decision states the trade-off and leaves the
choice to the maintainer rather than making it on their behalf.

**The architect is a trust root.** An
organisation owner can overwrite any secret and add themselves to
anything the organisation holds. That is not a gap in this design; it is
what "owner" means on GitHub, and no permission model can route around
it — someone has to hold the account that can fix everything, which is
exactly the account that can also break everything. A security model
that does not say this plainly is worse than one that does, because a
reader who is never told assumes the omission means the risk was not
seen.

**What this actually bounds.** This mapping does not close that gap —
nothing free on this hosting tier does. What it changes is the exposure window.
If `Write` is granted only to members who are actually active, and
revoked by a designated actor — the architect — as soon as someone
leaves an active role, the window during which an unused `Write` grant
sits ready to be misused goes from "for ever" to "the length of a term".
That is a real, useful bound. It is not the same property as "nobody with
write access can exfiltrate a secret", and this decision does not claim
it is.

## Rejected

**Leaving G-16 as governance prose, with no permission mapping.** A
promise that the role is "transferable" means nothing to a reader who
cannot see what, concretely, a successor is handed — or what a departing
Board member still holds the day after they leave.

**One flat collaborator tier for everyone.** Either every Board member
gets `Admin` — turning a voting seat into an organisation trust root, far
wider than the cockpit needs — or nobody gets real `Write`, which breaks
the write-as-yourself model the cockpit is built on (D-04).

**Describing this mapping as closing that gap.** It would overstate what a
free-tier access policy can do: environments, branch protection, required
reviewers and an effective `CODEOWNERS` all stay unavailable on a private
repository at GitHub's Free tier, whatever this project does with who
holds `Write`. Bounding an exposure and closing it are different claims,
and only one of them is true here.

## Cost

A second, "break glass" owner is a second full trust root: another
account that can rewrite any secret and add itself anywhere, held
precisely so it is *not* used — a real, standing widening of who can do
the most damage, accepted only to avoid the sharper failure of a single
lost account leaving nobody able to administer the organisation at all.

Handover is not instantaneous. Between promoting a successor and the
outgoing architect stepping down, two accounts hold owner at once — a
short window, deliberately not skipped, because verifying the promotion
before removing the only other owner is what keeps a botched handover
from locking everyone out.

Nothing enforces the `Write`-only boundary automatically once someone
joins the Board, and nothing revokes it automatically once they leave.
`docs/operating/operations.md`'s own *Inactivity (G-14)* section already
describes the manual checklist a departure requires; this decision is
what names who runs it — the architect, the only account with the
organisation-owner permission the checklist actually needs — rather than
leaving that unstated too.
