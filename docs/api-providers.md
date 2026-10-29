# Use an API provider

Choose a provider for API billing and an agent to do the work. Install that agent on the execution machine.

| Provider | Default agent |
|---|---|
| OpenAI | Codex |
| Anthropic | Claude Code |
| OpenRouter, Google and other providers | OpenCode |

OpenAI and Anthropic can also use OpenCode when selected under **Run with**.

1. Open **Settings → Agents & models → Connect API provider**.
2. Choose the execution machine and provider. OpenAI, Anthropic, Google, OpenRouter, xAI,
   DeepSeek, Mistral and Groq appear first. Other providers are available through OpenCode.
3. Enter a key, choose a model and **Save agent**. Leave the key blank to use an existing connection.
4. Choose that saved agent as the Lab default, for a role, for a study or for an individual task.

![Choose a provider and model; keys are entered privately](assets/current/api-provider.png)

Models come from each agent's own discovery: Codex's model list, Claude's supported model picker,
or OpenCode's refreshed Models.dev catalog and active registry. **Refresh models** reads it again.
Model versions are not hardcoded. You can also enter a configured model ID. If connecting changes
which catalog models are available, choose again.
Saving a key does not verify billing, model access or task performance; the first run tests those.

Codex and Claude API keys are saved in the execution account's private
`~/.arlotope/provider-keys.json` (`ARLOTOPE_HOME` can change this location). Only a selected API
agent receives the key. Claude uses `ANTHROPIC_API_KEY`; Codex uses its API-key login with in-memory
credentials for live sessions and `CODEX_API_KEY` for command runs. Normal CLI sign-ins stay in place.
Native policies and provider configuration still apply. Existing provider environment variables
can supply a key instead of saving one in the dashboard.

OpenCode connections use its native credential API and store, normally
`~/.local/share/opencode/auth.json`. Saved agents contain the provider and model choices, not keys.
Keys are not returned by the catalog, saved in browser drafts or added to the Lab's action log.
This is a local, same-account application, not a boundary against programs that can read that account's files.

For a remote project, connect its machine first. Its key stays on that host and travels over the
existing SSH connection. A saved agent is reusable; it does not pin work to a machine. Configure
its provider on every host where you use it. **Remove provider connection** removes the saved API
key on the selected host; environment-supplied keys are managed in that environment.

You can also enter a key from an interactive terminal without putting it in shell history:

```bash
./arlo api POST /api/providers --data '{action: connect, provider: openrouter}' --secret key
./arlo api GET /api/providers
./arlo api GET /api/providers --query provider=openai
```

The first read lists providers and harness choices; add `provider=<id>` for models. Native defaults
apply to writes too. Add `backend: opencode` (or `--query backend=opencode` for a read) to choose OpenCode explicitly.
Add `--query refresh=1` to refresh the model list, or `machine: <machine-id>` in a write body
(`--query machine=<machine-id>` for a read) to use a connected host. See [the local API](api.md)
for saving agent presets. Existing native OpenCode environment variables and custom providers
continue to work; see its [provider guide](https://opencode.ai/docs/providers).
