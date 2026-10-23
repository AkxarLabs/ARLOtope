# Tags

Tags help you find studies, tasks and reusable methods. They never choose an agent, start work, change a route or grant approval.

## Add and find labels

- In **New study**, expand **Tags & study ID**.
- On an existing study, edit its **Tags**. Use tag filters and search in **Studies** to find it later.
- In a workflow task, open **Connections & execution → Task tags**. Task search matches names and tags.
- Shared steps, workflows and procedures have their own tag fields. Shared edits still use the draft and publication process.
- Notes offer a **Tags** section. **Notes & sources** search matches record text and metadata.

Enter comma-separated labels. Spaces become dashes, letters become lowercase and duplicate labels are removed. Prefer a few useful labels, such as `replication`, `literature` or `dataset-a`. Reuse an existing spelling when it fits.

The Studies tag filter is saved in its URL, such as `#/studies?tag=replication`. Bookmark it or use Back and Forward to revisit filters.

## File and command reference

Study tags live in `IDEA.md` YAML frontmatter:

```yaml
tags: [replication, dataset-a]
```

Read or replace a study's tags without moving it:

```bash
uv run --with pyyaml python arlo.py tags my-study
uv run --with pyyaml python arlo.py tags my-study --set "replication, dataset-a"
```

Steps, workflows and composed tasks accept an optional `tags` list. Task tags override shared step tags for that workflow. Procedure tags belong in the skill's `arlotope` metadata; knowledge-record tags belong in their YAML frontmatter.

There is no separate tag database. Suggestions come from the current records and definitions. For the task controls, see [tasks and agents](agent-workflows.md); for note/source records, see [knowledge](knowledge.md).
