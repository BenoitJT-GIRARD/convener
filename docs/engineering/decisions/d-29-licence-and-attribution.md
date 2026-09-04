# D-29 — The licence is the AGPL; the name is not licensed at all

**Status:** Accepted

## Context

This product exists to be duplicated. Somebody copies it, edits a short list
of files, and runs their own seminar series on it for nothing. The people who
do that are volunteer-run scholarly societies: a mailing list, no budget, and
no lawyer to ask.

That audience arrives with three questions. Under what terms may they use it?
May a fork keep calling itself by this product's name? And does the line in
the footer that says who wrote the software mean anything, or is it decoration
a fork deletes in an afternoon? The first has a default answer and it is the
worst one available: copyright reserves everything unless something grants it,
so a repository with no `LICENSE` gives a reader who clones it no permission
to run the software, let alone to publish a modified version.

**The risk that matters here is not the one the question usually reaches
for.** Nobody is going to build a business reselling software that runs a
webinar series for a volunteer society. What does happen to tools this size is
quieter: an institution takes it, improves it, hosts it behind their own
sign-in for their own people, and never gives the improvements back. A few
years later the good version is the closed one, the original is a museum
piece, and every society that could have shared the work is maintaining its
own fork alone. **The risk is not that somebody resells this. It is that
somebody closes it.**

## Decision

Three separate instruments. Keeping them separate is most of the decision,
because conflating them is how a project ends up with a licence nobody can use
and a name nobody respects.

### The licence: GNU Affero General Public License, version 3 or later

Its section 13 is the whole reason. Under an ordinary copyleft licence,
running modified software on a server for other people is not conveying it, so
no source has to be offered — which is exactly the shape of the closure
described above. Section 13 says that making a modified version available to
users over a network obliges the operator to offer those users its source.
That is the one clause in the catalogue aimed at the failure this project
actually has.

`LICENSE` carries the official text, unmodified, exactly as the Free Software
Foundation publishes it. Nothing is trimmed and nothing is paraphrased: a
licence a court would have to reconstruct is not a licence.

**Version 3 *or later*, the form the Foundation itself recommends.** The
alternative pins this work to one document for ever, and correcting a defect
discovered in that document would then need the written agreement of everybody
who had ever contributed.

### The name: a term section 7 permits, and a document for whoever renames

Paragraph e of section 7 exists for precisely this — declining to grant rights
under trade-mark law — and it is the only way to hold a name back without
damaging the licence. The term sits at the head of `LICENSE`, above the
licence text, because section 7 requires an added term to be stated in the
files it applies to or to say where it is to be found; this one applies to the
covered work as a whole, so the file that carries the licence is where a
reader looks for it and where it can be read against the paragraph that
authorises it.

`TRADEMARK.md` is that term written for the person it lands on, and it is
four short lists: what the name and the mark cover, what stays an instance's
own identity, what a fork renames and what it keeps, and a closing line
asking that all of it be respected in good faith. It argues none of it. The
argument for holding a name back at all, and for holding it back this way, is
this record — which is where a reader who wants it can find it, and where it
stops standing between a fork and the four things it came to `TRADEMARK.md`
to look up.

### Attribution: an Appropriate Legal Notice, not a credit

Section 0 of the licence defines an Appropriate Legal Notice as a convenient
and prominently visible feature that displays a copyright notice, tells the
user there is no warranty, tells them a licensee may convey the work under
this licence, and tells them how to read a copy of it. Section 5 is what turns
that definition into a mechanism: a modified version's interactive interfaces
must display such notices **where the original's do**. So a product whose
interfaces display one obliges every modified version to keep displaying one,
and a product whose interfaces merely thank their author obliges nobody.

Both of this product's interfaces therefore display one, carrying all four
elements: the showcase's colophon, and the cockpit's own footer.

**Where its text lives.** `NOTICE.json`, at the repository root, beside
`LICENSE` and `TRADEMARK.md`. Everything the boundary declaration does not
hand to the instance belongs to the product by default
(`declarations/boundary.yml`, `tools/convener_ops/declaration/boundary.py`), so a file there
needs nobody to declare its owner. It is deliberately outside `instance/`,
which is the directory an operator opens in order to configure an instance: a
notice filed among the settings is a notice somebody eventually edits. And it
is deliberately outside `declarations/`, whose files the running product reads
in order to decide what it does — this one decides nothing, and is a sentence
the product says about itself. It carries no instance value for the same
reason: it names the software, its author, its licence and the absence of a
warranty, and it says the same words in every instance ever derived from here.
Two readers, one per side of the language boundary (D-14), and no third
spelling of the sentence anywhere.

## Rejected

**A Creative Commons licence.** Creative Commons advises against its own
licences for software, and the reasons are not academic: none of them
distinguishes source from binary, none of them deals with patents, and none of
them carries the warranty disclaimer software needs. The non-commercial
variants are worse than useless for this audience — the term has no settled
meaning, so an unpaid society inside a fee-charging university cannot tell
whether it is allowed to use this at all, while a company with counsel reads
the same words and carries on. It would deter exactly the people this exists
to serve, and stop nobody else.

**A source-available licence such as SSPL or a Business Source Licence.** Both
were written against one specific commercial threat: a very large cloud
provider reselling somebody's database as a managed service. Neither is
recognised as an open-source licence, which would keep this out of the
directories and mirrors an academic audience finds software through, and both
aim at a risk this project does not have. An unrecognised licence chosen to
defend against a hyperscaler that will never appear is a real cost paid for an
imaginary benefit.

**Making use of the name a condition of the licence.** That would be a
"further restriction" within the meaning of section 10: the result would not
be free software, could not be combined with other work under this licence,
and a recipient would be entitled to strip the condition anyway. Paragraph e
of section 7 is what keeps the same intention lawful and leaves the licence
whole.

**Registering the mark now.** An EU trade mark filed electronically at the
EUIPO in a single class costs about €850, and this project's first constraint
is that running it costs nothing. What that leaves is narrow: an action for
passing off in the United Kingdom, national unfair-competition rules across
the European Union, and no EU-wide unregistered right at all — each of them
turning on proof that the public already associates the name with this work,
established case by case, after the harm, at a cost this project has even
less of. Registration stays available later, and two things would end that
quietly: somebody else registering the same or a similar name for similar
goods first, and the word sliding into being the ordinary term for this kind
of software, which `convener` — the person who convenes a meeting — already
is in ordinary English. So the decision is reversible, and it is worth less
every year it is deferred.

**A footer line that only says who wrote this.** It has no effect on anybody
downstream. Section 5 carries a notice forward only if that notice is an
Appropriate Legal Notice in the sense section 0 defines, so a credit that omits
the warranty disclaimer, the permission to convey, or the pointer to the
licence text is precisely the decoration a fork deletes without breaking a
single rule.

**Letting an instance configure the notice.** It would turn the one thing a
modified version must not quietly empty into a field with a form beside it,
and it would file the product's own statement about itself among the values a
duplicate is told to overwrite before its first build.

**Putting a "Source" link in the notice.** Tempting, because section 13 is
about offering source and the licence's own closing guidance suggests exactly
such a link. It is deliberately absent. The source section 13 obliges an
operator to offer is the source of *the version they are running*, and a link
this product shipped would point upstream: right by accident on an unmodified
instance, and wrong in the product's own voice on a modified one, where it
would answer a user's request for the source with somebody else's source.
Section 0 does not ask for it, and the duty belongs to whoever modifies and
hosts.

## Cost

**Some organisations refuse the AGPL outright**, by policy, without reading
what the software does. That is a real loss of adopters, accepted because the
adopters it loses are the ones whose improvements would not have come back
anyway.

**A good-faith fork has to rename**, which costs somebody an afternoon and a
little goodwill, and the thing it buys — a reader always knowing whose
software they are running — is invisible when it works.

**The trade-mark position is weak, and stays weak.** An unregistered name
constrains nobody in advance, so what `TRADEMARK.md` asks of a fork acting in
good faith is the whole of what this arrangement gets from one that is not.

**Every page of both interfaces now carries three lines of legal text**, and
every fork inherits the obligation to keep carrying them. That is the
mechanism working as intended, and it is still an obligation this project
imposes on people it will never meet.

**The notice has to be true in two implementations, in two languages.**
`NOTICE.json` and one reader per side is what keeps that from becoming two
sentences free to disagree, and it is machinery that would not exist if the
line were displayed in only one place.

**Version 3 *or later* hands a document nobody here has read some authority
over these terms.** Accepted for the reason given above: the alternative
failure — a defect in the licence that can never be repaired — is worse, and
permanent.
