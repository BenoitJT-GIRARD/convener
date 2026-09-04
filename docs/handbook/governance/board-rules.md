# The Board's rules, in detail

You have just joined the Editorial Board. This page is the whole of what binds you: who may vote, how many yes votes a speaker needs, what happens if you do nothing, and what the system will never do to you or to anyone else.

It describes the rules **as the application actually applies them**. Where a number appears here, it is the number the code computes; where a rule says "never", nothing in the repository can produce the case.

**Why some rules carry a number.** *(G-01)*, *(G-05)*: these are the series' governance rules, numbered so that a commit message, a comment in the code, or another page can name a rule instead of paraphrasing it. The number is a handle; the rule is the prose beside it. Not every rule here has one, and some of the numbered rules are written on other pages and carry their number there. The table at the foot of this page names every one of them and the page it is stated on.

**What this page is not.** It holds no name and no count. Every rule below is written against *the Board*, whoever that is: the members, their joining days and their absences are in `instance/data/config.yml`, edited from the cockpit's own Board screen, and a series run by somebody else has a different Board and the same rules. That separation is the point — a rule that named a member would have to be rewritten every time one joined, and a page that carried a headcount would be wrong the day after the yearly meeting. Where the current Board's own composition is unusual enough to change how a rule *feels*, that is said on [The Editorial Board](editorial-board.md), next to the composition itself.

## Three things that never happen on their own

Start with these, because they are what makes the rest safe to read.

- **No automated process refuses a speaker.** The only status a scheduled job can write on a suggested speaker is *parked* — kept for later. Declining is an act a named member takes.
- **No automated process removes a member, and no nomination is ever refused.** The outcomes a nomination can reach are *accepted*, *deferred* and *waiting*. There is no rejected outcome anywhere in the vocabulary, so none can be written by anybody, human or otherwise. A nomination the Board does not carry is *deferred*, which moves the question to a meeting and closes nothing against the person. The yearly inactivity check *proposes*, prints its proposal, and has no way to apply it.
- **The scheduled job cannot sign a decision.** Every decision is recorded as a commit naming the member who took it, and the nightly job has no login to sign with. Anything that has to be signed is therefore something a person did.

## Who votes, and how many yes votes are needed

### Who counts

Each vote is counted over the **eligible Board** on the day it is counted:

- every member whose entry is **active**;
- **minus** anyone who has declared themselves away over that day;
- **minus** anyone who has recused themselves on that particular speaker.

An **abstention stays in the count**. That is what gives the two-thirds bar its meaning: abstaining makes a yes harder to reach, it does not step aside. Only a recusal steps aside.

A member who is away is still a member — they are simply out of this vote. And a ballot from someone who is not on the Board is not counted at all.

### The bar (G-01)

**Two thirds of the eligible Board, rounded up, and never fewer than three yes votes.**

| Eligible members | Yes votes needed |
|---|---|
| 3 | 3 |
| 4 | 3 |
| 5 | 4 |
| 6 | 4 |
| 7 | 5 |
| 8 | 6 |
| 9 | 6 |

The floor of three matters: without it, three recusals on a Board of six would quietly bring the bar down to two voices.

**Below three eligible members the vote is suspended**, not decided. No number of yes votes carries a speaker while the Board is that small, and the window running out does nothing either — the question simply waits.

**The bar is never written down.** There is no threshold field in any file. It is recomputed from the ballots and the Board every time a screen is drawn, so it cannot drift away from the Board it claims to describe. If someone declares an absence, the bar moves that instant, for everyone looking.

You cast one ballot per speaker. Changing your mind replaces your ballot; it never adds a second one.

This bar decides a speaker. What it takes to appoint a member of the Board is a different number, and it is under *Joining the Board* (G-05).

## The vote window, and what parking means (G-02)

The window is **14 calendar days** from the day the Board was asked. Weekends count.

- The moment the yes votes reach the bar, the speaker is **approved** — by the ballot that reached it, not by any later process. There is no separate closing step.
- The last day of the window is still a day on which you may vote. Nothing can expire before it has passed.
- If the window runs out and the bar was not reached, the lead is **parked**. Parked is not a refusal: it means *kept for later*, and any Board member can put it back to a live question with one click.
- If the vote was suspended (fewer than three eligible), running out of days changes nothing at all.

A refusal is always a deliberate act by a named member. The clock cannot produce one.

## Standing aside: recusal (G-03)

Any voter may recuse themselves by declaring a conflict of interest, and doing so takes them **out of the count** — which lowers the bar for everyone else.

- **A written reason is required.** A recusal without one is not recorded; the control stays unavailable until you have written a line.
- **Whoever suggested the speaker is not excluded automatically.** In a narrow field, proposing someone you know is normal; excluding proposers by reflex would shrink the count for no reason. Recusal is the general mechanism, and it covers that case like any other.

The reason you write stays with the speaker's record, where it can still be corrected. It is never copied into the derived register, which holds only acts and dates.

See also the [conflict-of-interest policy](conflict-of-interest.md), which is about the *speaker's* interests; this section is about yours.

## A conflict that comes to light afterwards

If it turns out that a member voted while holding a conflict they had not declared, any Board member records it against that speaker, naming the member and writing what the conflict was.

What then happens, exactly:

- that member's ballot becomes a **recusal**, carrying the reason, who recorded it and on what day. Their own comment is kept — one member's action does not erase another's words;
- the Board's acceptance is **cancelled**. The speaker goes back to being a suggestion and the window opens again from that day;
- **the vote is not re-decided**, even when the remaining yes votes would still clear the now-lower bar. The acceptance was reached on a false basis, so it goes; whether the Board approves the speaker again is a fresh question, answered by fresh ballots.

The system refuses to record this if there is no written reason, if the person named is not an active member, or if that person had already recused themselves — in which case nothing was concealed and their ballot is already out of the count.

It cannot be recorded against a talk that has already been given, or against a speaker who withdrew themselves: there is no acceptance left to cancel.

Nothing about the incident is written to anyone outside. The register records that the vote was reopened and by whom; the reason stays with the record, visible to the Board.

## Joining the Board

### Who may be nominated

Anyone who has **co-hosted at least two webinars that actually happened**. That is counted from the event records themselves — not declared anywhere, and not something a Board member can assert. Webinars still to come do not count yet.

A Board member opens the nomination, naming the candidate by their GitHub username. You cannot nominate someone already on the Board, and you cannot open a second nomination for someone whose nomination is still an open question. Opening one records your own support for it: nobody puts a candidate forward and then leaves them unbacked.

### The Board has to say yes (G-05)

A nomination is a question put to the Board, and it carries only when the Board answers it.

**The window is 14 calendar days** from the day the nomination was opened. It is the length the vote window already has (G-02) and the length the series already gives itself to decide on a suggested speaker (G-09): all three are the Board being asked to express itself, and one number is easier to keep than three.

**The bar is a majority of the eligible Board, and never fewer than three supports.**

| Eligible members | Supports needed |
|---|---|
| 3 | 3 |
| 4 | 3 |
| 5 | 3 |
| 6 | 4 |
| 7 | 4 |
| 8 | 5 |
| 9 | 5 |

Eligible is counted here as it is counted for a speaker, without the recusal, which belongs to a speaker's record: every active member, minus anyone who has declared themselves away over the day the count is taken. A member who is away is still a member, and the bar moves with them the moment they declare.

**The bar for a speaker and the bar for a member are two numbers.** Two thirds of the eligible Board approves a speaker (G-01); a majority of it appoints a member. Nothing converts between them.

The floor of three is what a majority on its own does not give you: half of a Board of two is one, and one member seating another is the whole of what this rule exists to prevent. **A Board with fewer than three members able to vote appoints nobody**, and the question goes to the meeting instead.

**Silence counts as refusal.** A member who has said nothing has not agreed, and no length of waiting turns their silence into a yes. So:

- the moment the supports reach the bar, the nomination has carried, and a member records it. The Board screen says which nominations are due and a member presses the button; no scheduled job seats anybody. The Board produces the outcome; a person writes it down.
- a support recorded after the window has closed does not count. The days are the whole of the chance the Board is given.
- if the days run out below the bar, the candidate is **not appointed** and the nomination is **deferred**: the question goes to the Board's next meeting, or to the yearly one.

If the Board is already at its maximum size, a nomination that has carried becomes **waiting**. Waiting is a question about room and says nothing about the candidate: it is re-examined every time the Board changes, and the candidate is seated as soon as a seat frees.

**The candidate is written to.** A member writes to them, says the nomination did not carry, and says where the question goes next. This page holds no wording for that letter: it is addressed to one person about a decision about them, and a form of words published here would turn it into a form letter. Nothing in the repository records that it was sent.

**A candidate still inside the window when the meeting comes stays inside it.** Nothing stored says a meeting happened, so nothing here turns on one: the window runs the days it has, and the members who are in the room record their support there like anybody else.

### Objecting, and what deferral means

Any active member may object, in writing. An objection:

- **requires a reason** — one line is enough, and it is kept on the record;
- **closes the window early.** It defers the nomination to the yearly meeting there and then, with the objection and its author on the record. That is why both the reason and the name are required.

A second objection from the same member replaces their first rather than stacking, and a member who had recorded support and then objects has that support taken off: nobody is counted on both sides of one question.

**While an objection stands, the nomination cannot be re-opened.** A fresh nomination for the same person is refused, and the app says why and who objected. Otherwise an objection could be routed around by nominating the same person again a minute later, which would empty the deferral of its purpose.

The way forward is that **the objecting member withdraws their own objection** — and only they can. Nobody can withdraw anyone else's, and no delay clears one. When the last objection on a nomination is withdrawn, the nomination is open again and **the 14 days start again from that day**, so the rest of the Board gets a real window on a question they had been told was already settled. The supports already on the record stay on it: a member who said yes said yes, and somebody else's objection being lifted is no reason to ask them again.

A nomination deferred because its window ran out carries no objection, so there is nothing for anybody to withdraw. The way back to it is a fresh nomination, which the meeting is free to call for.

The yearly meeting acts through that same door: a member whose objection the meeting does not uphold withdraws it, and the nomination resumes. If nobody withdraws, the deferral simply stands and the meeting can take it up again. There is no field anywhere recording that a meeting happened, and none was invented for this — a rule that turned on a date nobody writes down would be a rule nobody could rely on.

## Stepping back: absence, and inactivity

**Declaring an absence (G-06)** is something you do for yourself. You give the last day you are away — that day included — and you are out of every count until it passes. You come back on your own: there is nothing to write, and nothing to remember. There is no proxy and no vote by delegation.

**Inactivity** (G-14) is the other half. A member who has cast no ballot for the configured number of months stops counting toward the bar, so a Board of five that has really been four for a year stops needing four voices to agree.

Nothing about this happens on its own. The nightly job computes the proposal and prints one line per member; **no command applies it**. A person applies it, or nobody does, and the yearly meeting is what settles the question. The full description, including the three things the rule will not do, is in `docs/operating/operations.md` ("Inactivity").

Inactive is not a departure and not a judgement. The seat is kept, the entry stays in the file with the day you joined intact, and coming back is one word changed back. A member re-seated through a nomination is reactivated in place rather than added a second time.

## Being on the Board is not the same as owning the organisation

A Board seat and a GitHub permission are different things, granted by different people. Being on the Board makes you eligible to vote; it never, on its own, changes what your GitHub account can do here.

Two roles, on two separate GitHub scopes: the **architect** is the organisation's owner — independent of Board membership, able to add or remove anyone and change any repository setting — and a **Board member** holds repository **write**, and nothing more. Casting a ballot through the cockpit writes with your own signed-in token, so write is the floor the tool actually needs; it is not admin, and it is not a step toward it. Joining the Board does not grant it, and stepping back from the Board does not remove it — both are separate, manual acts by the architect. The full mapping, including why one person ultimately has to hold a role this wide, is [D-28](../../engineering/decisions/d-28-architect-and-board-permissions.md).

## Publishing a recording: two permissions, and they are not alike

**Why there is a second gate at all.** The Board has already said yes to this speaker, so it is fair to ask what is left to decide. The answer is that the session and the recording are not the same object. A session is heard once, by the people who came, and then it is gone; nobody can be sent back to it, and nothing about it can be found by someone who was not there. A recording is the opposite in every respect. It sits under the series' name for as long as the channel exists, it is what a stranger finds first, and it goes on speaking for the speaker long after everyone who organised the day has moved on. We do not carry the same responsibility for the two. An hour that went a little wrong in the room is an hour that went a little wrong; the same hour published is a standing statement that we are content for it to represent us and the person who gave it. So the second gate is not a second opinion about the speaker — that question was settled — it is the first decision anyone has taken about the recording, which is a different thing, decided once, by people who have watched it.

**This is also why it is quick.** It asks a member to look at a specific and finite list — a conflict of interest that was not declared, commercial content that turned into a pitch, something said in the room that should not follow the speaker around — and then to get out of the way. It is three working days and one approval, not a review. Treating it as a formality is the mistake it exists to prevent; treating it as a hurdle is how it comes to be routed around, which costs more.

A recording goes online only when **two separate permissions** are in hand, from two separate parties. Neither can be read off the other.

### The speaker's — which must be present (G-07)

Ask them, in writing, and record the answer. Only two answers can be recorded: **granted** or **refused**.

- **Silence is never consent.** Nothing about waiting produces it — the rule that reads the speaker's answer is not even given today's date, so "enough time has passed, so they must agree" is not a sentence the system can express.
- A **refusal takes the recording down** on the spot if it was already online, and it can be given at any time. A speaker may change their mind after publication.
- A record with no answer yet is exactly as blocking as one with no answer ever.

### The Board's — which must be absent (G-08)

Here it is the **objection** that has to turn up, and silence does clear the way.

- One Board member approves, by name and on a named day. That is what starts the clock.
- Any other member may object within **three working days**, in writing. Weekends do not count.
- Once those three working days have passed with no objection standing, this half is cleared.

An objection stops publication, and takes down a recording that was already online. It is closed by a member either **lifting** it or deciding the talk is **withheld**, with a written note kept beside the original objection. There is deliberately no "publish" way of closing an objection: lifting it returns the record to the gate, it does not walk through it.

Publishing itself is then a member's act, and it asks the gate first. If either permission is missing, the control stays unavailable and the screen says which one — the speaker's is reported first, because it is the one nobody on the Board can give on their behalf.

## How the days are counted

Two units are in use, on purpose, and nothing converts between them.

| Window | Unit |
|---|---|
| Publication objection window (3) | **Working days** — weekends skipped |
| Vote window (14) | Calendar days |
| Nomination window (14) | Calendar days |
| Turnaround targets (14 / 30 / 7 / 14) | Calendar days |

Reading a calendar window as working days would stretch fourteen days into twenty; reading a working-day window as calendar days would shorten it across every weekend. Either way a real deadline moves by real days, so the unit is stated wherever a window is.

**Public holidays are deliberately not modelled.** The Board's members do not all work under the same national calendar, so a holiday list that was right for one country would be wrong for the others. An unmodelled holiday only ever makes a window effectively *longer*, which is the prudent direction, and the tests pin it.

Every date in the system is a **Paris calendar day**, everywhere, so a member reading the app late at night in another time zone sees the same day as the nightly job.

### The turnaround targets (G-09)

Four steps have a target time: a decision on a suggested speaker (14 days), a follow-up on an invitation with no answer (30), a forum summary after the talk (7), the recording after the talk (14).

**Nothing happens when one passes.** It produces a line of text and a place in a sort order. It parks nothing, refuses nothing and writes nothing. And the sentence is always about the piece of work — *"Board decision is 3 days overdue"* — never about a person: there is no room in the wording for a name, so none can appear there.

Where the record does not hold the day a clock would start from, **there is no deadline** rather than a guessed one, and those items sort last instead of first.

## The numbered rules, and where each one is stated

**What a number is.** A rule's number is its place in one walk of the documentation: the three trees in the order `docs/README.md` lists them, the pages of a tree in path order, and the rules of a page in the order they are written. A number says where a rule is written and nothing about how much it binds you, which is why the first row below is the two-thirds bar and the last is the handover of an account.

**A rule written between two others takes the number of its place**, and the rules after it move up one. Nothing outside this repository cites these numbers, and `tools/tests/repository/test_cross_references.py` fails on any citation a move leaves behind.

**A rule that is withdrawn keeps its number.** It comes off its page, the number is declared retired in `tools/scripts/generate_rule_index.py`, and no later rule takes it. Those numbers are listed under the table, so a citation of one still leads somewhere.

<!-- BEGIN GENERATED RULE INDEX -- tools/scripts/generate_rule_index.py -->
*The table below is generated from the pages themselves: every rule that
carries a number, what its own page calls it, and where it is stated. Do not
edit this block — run*
`uv run python scripts/generate_rule_index.py`
*from `tools/` and commit what it writes.*

| Rule | What it is | Stated in |
|---|---|---|
| G-01 | The bar | `docs/handbook/governance/board-rules.md` |
| G-02 | The vote window, and what parking means | `docs/handbook/governance/board-rules.md` |
| G-03 | Standing aside: recusal | `docs/handbook/governance/board-rules.md` |
| G-05 | The Board has to say yes | `docs/handbook/governance/board-rules.md` |
| G-06 | Declaring an absence | `docs/handbook/governance/board-rules.md` |
| G-07 | The speaker's — which must be present | `docs/handbook/governance/board-rules.md` |
| G-08 | The Board's — which must be absent | `docs/handbook/governance/board-rules.md` |
| G-09 | The turnaround targets | `docs/handbook/governance/board-rules.md` |
| G-10 | This log, and the register next to it | `docs/handbook/governance/decisions.md` |
| G-11 | Diversity | `docs/handbook/governance/selection-criteria.md` |
| G-12 | Registration | `docs/handbook/governance/traitement-donnees.md` |
| G-13 | The conflict-of-interest slide | `docs/handbook/toolkit/run-of-show.md` |
| G-14 | Inactivity | `docs/operating/operations.md` |
| G-15 | The Board's target size | `docs/operating/operations.md` |
| G-16 | Handover | `docs/engineering/architecture.md` |

And the numbers no rule carries any more. Each was a rule once, and no later
rule takes it:

- **G-04** — Joining the Board, under which a nomination carried on seven calendar days of silence. Withdrawn on 2026-09-04, when the Board's own agreement became what appoints a member.
<!-- END GENERATED RULE INDEX -- edit tools/scripts/generate_rule_index.py, not this block -->
