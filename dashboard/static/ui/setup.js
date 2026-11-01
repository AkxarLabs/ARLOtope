/* Agent connection is optional; study creation is independent. */
(function () {
  const NL=window.NL, {html}=NL;
  NL.SetupPage=()=>html`<div class="page page-narrow"><h1>Connect an agent</h1>
    <p class="lede">ARLOtope runs the agent programs on this computer, signed in with your own account. One is enough.</p>
    <${NL.AgentsSignIn} /><p><a class="link" href="#/settings/agents?connect=acp">Connect another agent with ACP →</a></p><section class="process-primer"><h2>Run controls</h2><${NL.LaunchSwitch} /></section>
    <div class="starter-actions"><a class="btn" href="#/settings/autonomy">Limits & permissions</a><a class="btn btn-primary" href="#/start">New study</a></div>
    <details class="more"><summary>Configure the lab in a conversation</summary><p>For detailed research interests, compute and methodology preferences, use the optional setup interview.</p>
      <${NL.Btn} onClick=${()=>NL.launch({skill:'setup-lab'})}>Start setup interview</${NL.Btn}></details></div>`;
})();
