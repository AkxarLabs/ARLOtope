# Getting started

Create a study, give an agent one useful task, and inspect its answer. You can add a more detailed research process later.

## 1. Open the Lab

From the repository folder, with Git and uv installed, run:

```bash
uv run --with pyyaml python newts.py
```

The platform launcher opens the same application. The browser connects to a local server, normally on `http://127.0.0.1:8787`. Agent requests use the accounts configured in their own tools.

If you want dashboard-managed tasks, choose **Connect an agent** in the Lab or open **Settings → Agents & models**, then install or sign in to a harness. Enable agent runs in **Settings → Limits & permissions** when you are ready to launch work. You can create a study and browse its files before doing this.

![The visual Lab before starting work](assets/current/lab-light.webp)

*Demonstration fixture: the Lab is the main workspace. Start a study from the top-right button.*

## 2. Enter study details

Choose **New study**, then select the starting point inline:

- **A research question** for a topic or first task without an attached repository.
- **An existing project** for a folder on this computer or a connected machine. Choose the machine and use **Browse…** to select the folder.
- **A GitHub repository** for an exact public `owner/repository` or repository URL. Press **Look up repository**, then review the new working-copy location. For a private repository, clone it with your normal tools and attach the existing folder.

Fill in **Study title** and **What would you like to investigate?** Choose a **Starting workflow**. Selecting a starting point reveals its fields on this page; it does not create the study.

![New study details with starting-point choices and research fields](assets/current/start-details.webp)

*Demonstration fixture: study details before saving. Use your own question and project location.*

Expand **Brief & materials** if you have a brief, papers, notes or images. Uploading files does not launch an agent. The limits shown in the form are 5 MB per file and 20 MB per draft. Optional **Agent help → Suggest study details** does launch an agent turn; review its proposal before **Apply suggestion**.

**Tags & study ID** and **Agent choices (optional)** can remain at their defaults. The latter saves study-level agent preferences; it is separate from the agent used for an optional suggestion.

## 3. Review and create

Press **Review study**. Check the question, workflow, files, machine and project path. Use **Back** to correct anything.

![Reviewing a demonstration study before creation](assets/current/start-review.webp)

*Demonstration fixture: the review page makes the proposed study and attachment visible before creation.*

Choose **Create study**, or **Clone & create study** for GitHub. Attaching a folder adds Lab registration files; existing code and environment stay in place. Cloning downloads source without installing dependencies or running repository code. Creating a study does not start a research agent or approve a checkpoint.

## 4. Start one task

After creation, choose **Plan the first task with an agent**. Review the prefilled instruction, choose an agent if needed, then launch from the task dialog. **Open study** lets you inspect the record first.

![Created study with a separate first-task action](assets/current/start-created.webp)

*Demonstration fixture: creation and agent launch are separate actions.*

A useful first instruction for an existing project is: “Read the project instructions and explain the current pipeline, evidence and open questions before proposing changes.” For a new question, ask for a focused plan with success criteria and a small first check.

![Reviewing the first instruction before launching an agent](assets/current/start-task.webp)

*Demonstration fixture: inspect the instruction and agent options before sending.*

## 5. Inspect the conversation and result

Open the task's conversation from the study or **All agents**. Answer a pending question there or in **Inbox**. Tool permissions and research checkpoints are separate decisions. If a task stopped without completing its assigned outcome, inspect the record before using **Continue task** or **New agent with handoff**.

![Demonstration agent conversation and recorded activity](assets/current/agents-run.webp)

*Demonstration fixture: inspect what the agent actually recorded, rather than treating a finished turn as a verified result.*

Published pages appear in **Library → Outputs**; existing files are in **Documents**. **Notes & sources** holds separate notes and saved workspace Q&A. **Visual summary** on a run starts an independent explainer and leaves that run untouched.

Next: [dashboard tour](dashboard.md), [tasks and agents](agent-workflows.md), or [customize a workflow](customising.md).
