# ACP agents

Lab’s optional Agent Client Protocol (ACP) adapter connects an agent executable over JSON-RPC on
stdio. It sits alongside the native Claude Code, Codex and opencode adapters. Lab still owns the
study, workflow, queue and checkpoints.

## Connect an ACP agent

1. Install the ACP server or adapter documented by your agent vendor. An editor’s launcher is not
   necessarily its ACP command.
2. Open **Settings → Agents & models → Add preset**. Choose **acp** as the harness.
3. Enter the executable and arguments as a JSON array. Use **Keep preset**, then **Save agent choices**.
4. Choose **Test**. This negotiates the protocol without sending a model prompt.
5. Assign the preset as a default, by role, or for one task.

![Saved agent presets in Settings](assets/current/agent-presets.webp)

A preset can use a wrapper script to prepare its environment:

```yaml
# Under agents.programmatic.presets in lab/config.yaml
my_acp:
  label: My ACP agent
  backend: acp
  command: [/absolute/path/to/agent, --acp]
  # auth_method: an authentication method offered by this server
```

Use the server’s documented Windows executable path on Windows. Command arguments are not a shell
command string. Provider credentials belong to the agent; an editor login may not authenticate a
separate ACP server.

For a remote project, configure **Agents & commands → Custom command** on the execution machine.
Local executable paths and credentials are not copied there. See [remote projects](remote-projects.md).

## What the adapter does

The adapter negotiates protocol version 1 and advertises text-file access, terminal tools and
supported form/URL elicitation. It supports new sessions, prompt turns, streamed text/tool updates,
permission requests, cancellation and usage updates. The agent may also supply its own tools.

Client file and terminal calls use the execution account’s access and applicable Lab hooks. This
is not an isolated filesystem or an OS sandbox for untrusted agents.

Permissions offer a matching **allow once** or **reject once** choice. A one-time decision never
becomes a persistent grant. If the server offers no matching one-time choice, Lab cancels the request.
Research checkpoint approvals remain separate.

## Questions and external flows

Forms appear in the run conversation and Inbox. Supported fields retain typed values, defaults and
constraints. **Send answers**, **Decline** and **Cancel request** have different meanings; closing the
conversation does not answer it. Several requests can wait together.

URL requests show the address and host before **Open link**. Lab does not prefetch the page for the
model. Opening it does not establish successful authentication; the server’s matching completion
notification is recorded separately. Use the provider’s authentication flow for credentials:
ordinary form answers are agent-visible data.

Plain-text questions can also be answered in the conversation. An ended workflow turn without an
accepted outcome appears as **Task unfinished**, even when no explicit question was asked.

![A run conversation and its controls](assets/current/agents-run.webp)

## Resume, models and forks

| Choice | Requirement |
|---|---|
| Continue a stopped session | Server advertises session loading |
| Explicit model | Requested ID appears in the server’s session configuration options |
| Native fork | Server advertises the optional fork capability |
| New conversation with evidence handoff | Separate fresh session; does not clone the full conversation |

Unsupported choices fail explicitly. ACP has no one-shot fallback. Native CLI effort and
permission-mode flags do not configure an ACP session; agent-specific startup flags belong in the
command array. Other settings remain in the agent’s own configuration.

Refusals and output/turn limits are reported as failures. Tool failures remain visible in the run.
Published summaries use the same [Library outputs](artifacts.md) as the native adapters.

## Verification scope

Deterministic protocol peers exercise sessions, questions, permissions, client tools and failures
without provider credits. Recorded live checks include initialization/session creation with an
installed opencode ACP server, and a Windows Antigravity ACP text turn followed by loading that
session. The opencode handshake check did not send a model prompt; the Antigravity text check used
no tools. These checks do not establish every vendor’s forms, tools, model access or native forks.

The implementation references stable v1
[initialization](https://agentclientprotocol.com/protocol/v1/initialization),
[sessions](https://agentclientprotocol.com/protocol/v1/session-setup),
[permissions](https://agentclientprotocol.com/protocol/v1/tool-calls) and
[elicitation](https://agentclientprotocol.com/protocol/v1/elicitation).
Check your installed server’s capabilities and vendor instructions when configuring it.
