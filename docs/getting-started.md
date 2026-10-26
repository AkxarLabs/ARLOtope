# Your first study

Bring a question or an existing project, give an agent one task, and inspect its work.

## 1. Open the Lab and connect an agent

With Git and uv installed, clone the application and run it:

```bash
git clone https://github.com/AkxarLabs/ARLOtope.git
cd ARLOtope
uv run --with pyyaml python arlo.py
```

There is no template-generation step. First use creates this clone's private `lab/config.yaml`
from `lab/config.defaults.yaml`. Existing settings are preserved. A second clone can be a separate
Lab; cloning an existing Lab's source does not copy its ignored research records.

You can also use `./arlo` on macOS/Linux, `.\arlo.cmd` on Windows, or the platform launcher.
The browser normally opens at `http://127.0.0.1:8787`. Add the repository to PATH to use `arlo`
from another folder.

**Show me around** opens the ARLO guide on your first visit. You can return through **?** in the
header. The guide explains the main pages without changing settings or starting work.

![The ARLO guide introduces agent setup](assets/current/arlo-guide.webp)

For managed tasks, open **Settings → Agents & models** and sign in to an installed agent.
Use **Connect ACP agent** for another compatible tool. Enable launches in **Limits & permissions**
when ready. You can create studies and read their files before enabling agents.

## 2. Create a study from the work you have

Choose **New study**, then select:

- **A research question** to start without a repository.
- **An existing project** to attach a folder. Choose its machine and use **Browse…**.
- **A GitHub repository** to clone by name or URL. **Choose repository** lists repositories available
  through GitHub CLI; **Connect GitHub** opens sign-in if needed. Public URLs work without it.

Enter a title and question. **Add a brief or files** accepts supporting materials. Uploads do not
start an agent. **Agent help → Suggest study details** uses an agent turn; review its suggestion
before applying it.

![Study details with a question and project choices](assets/current/start-details.webp)

The **Starting workflow** map shows what will happen. Select a task to inspect it, or open
**Change workflow**. Already have useful work? Choose **Use existing work** on the relevant task
and supply references. **Skip at start** leaves a task out without claiming it is done; no reason
is required. These choices apply at the beginning. If a later loop returns to the task, it runs
normally. Checkpoints still apply.

![Choose existing work on a workflow task](assets/current/workflow-start.png)

Leave **Study settings** closed to use default agents and tags.

## 3. Review and create

Choose **Review study**. Check the question, workflow, files, machine and folder, then **Create study**
or **Clone & create study**. Use **Back** to correct anything.

![Review the study before creating it](assets/current/start-review.webp)

Creating a study does not start an agent. Attaching a folder preserves its code and environment;
cloning downloads source without installing dependencies or running it. **Files added to this
project** explains the registration records. See [what to keep in Git](knowledge.md#what-to-keep-in-git).

## 4. Start one task

Choose **Open study**. Start its next task, or use **Run ready tasks** for a workflow with ready
branches. The saved workflow supplies the instructions and agent choices.

For a preliminary conversation, choose **Plan with an agent** instead. Review the instruction and
study, change the agent under **Options** if needed, then **Send**. This starts a separate task;
it does not run the workflow automatically.

![Open a created study or plan with an agent](assets/current/start-created.webp)

For an existing project, a useful first instruction is: “Read the project instructions and explain
the current pipeline, evidence and open questions before proposing changes.”

## 5. Follow work and read its results

In **Lab**, click an agent to see its task and open its conversation. **All agents** lists sessions;
**Inbox** holds questions, permissions and decisions. If an agent stops without completing its task,
inspect the attempt before **Continue task** or **New agent with handoff**.

![An agent conversation and its recorded activity](assets/current/agents-run.webp)

**Library → Outputs** shows published pages, including interactive HTML. **Documents** shows existing
files; **Notes & sources** holds retained notes and saved Q&A. A run's **Visual summary** starts a
separate explainer without interrupting its agent.

Screenshots use example studies. Next: [dashboard tour](dashboard.md),
[build a workflow](agent-workflows.md), or [recover interrupted work](recovering-work.md).

Before collecting research, choose a backup location for your [Lab and project records](projects.md#storage-updates-and-backups).
