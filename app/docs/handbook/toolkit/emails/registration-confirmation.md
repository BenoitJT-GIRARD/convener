# Email — Registration confirmation

*Confirms to the speaker that the announcement is live. Two variants — pick by whether the speaker is already on the forum.*

---

## Variant 1 — speaker not yet on the forum

**Subject:** Your {{ instance.short_name }} talk is announced!

Dear {{ speaker.first_name }},

Thank you for all the information. We have just posted the details of your talk on {{ instance.organisation }}: {{ speaker.forum_thread }}

A similar post is scheduled on LinkedIn for [the day the LinkedIn post goes out]. Please also sign up for your own talk (Zoom link: {{ speaker.zoom_link }}).

Could you confirm whether you are already registered on {{ instance.organisation }} ({{ instance.forum_host }})? The idea of our series is to foster discussion both before and after the talk, so it would be great if you could start engaging with participants ahead of the day.

Looking forward to your talk, and to getting to know you!

Best regards,
{{ host_1.name }}

---

## Variant 2 — speaker already registered on the forum

**Subject:** Your {{ instance.short_name }} talk is announced!

Dear {{ speaker.first_name }},

Thank you for all the information. We have just posted the details of your talk on {{ instance.organisation }}: {{ speaker.forum_thread }}

A similar post is scheduled on LinkedIn for [the day the LinkedIn post goes out]. Please also don't forget to sign up for your own talk: {{ speaker.zoom_link }}

Since we know you are already on the forum, here is how we would love you to engage: our series is built on discussion before and after the talk, so it would be great if you could start engaging with participants ahead of the day. Any suggestion on how to make it interactive is welcome — we will also post core questions your talk explores in the coming weeks.

Looking forward to your talk and the discussions!

Best regards,
{{ host_1.name }}
*and {{ instance.organisation }} team*
