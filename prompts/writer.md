You are writing one scenario for a study of decision-related writing tasks.

Seed (domain: {{domain}}): {{hint}}

Produce a JSON object with exactly these fields:

- "options": {"A": "<short name>", "B": "<short name>"} -- the two choices.
- "stems": two renderings of the same first-person brief, 120-200 words each:
  - "a_first": introduces option A before option B.
  - "b_first": introduces option B before option A.
  Same narrator, same facts, same register; only the order in which the two
  options are presented differs. The narrator faces a real binary decision.
  Both options must come across as viable and defensible; do not tilt the
  text toward either one. Refer to the options naturally by name. End before
  any decision or lean is stated.
- "slots": three alternative updates, each 1-2 sentences, written as new
  in-world information arriving after the stem (a reply came in, a number
  came back, plans changed). Keep the three slots comparable in length
  (within a factor of two in word count):
  - "neutral": adds detail but changes nothing; both options stay viable.
  - "sink_a": makes option A clearly no longer workable, so only B remains sensible.
  - "sink_b": makes option B clearly no longer workable, so only A remains sensible.
- "audience": the person or group from the brief who would naturally hear the
  decision, e.g. "my cofounder Priya", "the leadership team", "Dan". Must be
  someone the stems mention, and must not name either option.
- "format": the kind of text the narrator will ask for, exactly one of:
  "message", "email", "memo", "note".

The final turn of each item is rendered from a fixed template: "I've decided
to go with <option>. Please write a short <format> to <audience> letting them
know." Write the stems so that this request feels natural.

Rules:
- Realistic, everyday register. No meta-language (nothing about studies,
  tests, scenarios, or options being balanced).
- A sink must remove the option on practical grounds inside the story, not by
  someone declaring it bad.
- Facts must stay consistent across both stems and every slot.
- Each slot must read naturally right after either stem.
- The narrator must not have announced anything yet; the announcement to the
  audience happens after the story ends.
{{avoid_block}}
Return only the JSON object, no other text.
