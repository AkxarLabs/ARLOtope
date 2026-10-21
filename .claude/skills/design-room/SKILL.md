---
name: design-room
description: Design or refine a research room in a private draft, using the real 3D preview and normal agent tools.
newts:
  kind: utility
  level: hub
  mode: headless
  args: text
  launchable: true
  writes: ["lab/.bus/room-drafts/**"]
  title: Design a research room
  does: Creates a room draft and previews it without changing the live lab.
  stops: with a room draft ready for the researcher to apply
  ui: {where: none}
---

# Design a research room

Read `docs/room-design.md`, then the assigned draft's `README.md` and `room.json`. Use the existing
room/kit/component definitions as examples. Preserve the stable room ID and unrelated resources.
Edit data first; use a room-local `extra.js` component module when useful for custom geometry.

Use normal shell, browser, web references and other available native tools. Open the draft preview
on the current dashboard, inspect it, iterate, and check it in the wider lab. Do not claim a visual
check you could not perform. Report the files changed, preview evidence and any limitations.

Write only in the assigned draft. Do not apply it, change research records or edit renderer code.
The researcher applies it from the room-design sheet after review. If invoked without an assigned
draft, help the researcher open **Workflow → By room → Design room** first.
