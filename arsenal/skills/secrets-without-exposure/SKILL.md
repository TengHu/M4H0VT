---
name: secrets-without-exposure
description: Use whenever a program or AI agent must use a token, API key, password, private key, DSN or other sensitive data without the value being seen, printed, logged, committed, or placed in an LLM context window. Covers runtime injection, secret managers, opaque types, credential-injecting proxies, hardware-held keys, keyless/OIDC auth, redaction, and agent-specific tooling.
---

# Secrets Without Exposure

> **Core principle:** pass around a *reference* to the secret, never the *value*.
> The value is resolved at the last possible moment, inside the one component
> that is allowed to hold it, and nothing downstream (code, terminal, logs,
> chat transcript, LLM context) ever receives it.

---

## 0. Rules for the agent reading this skill (MUST follow)

1. **Never print, echo, cat, log, or return a secret value.** No `cat .env`,
   `echo $TOKEN`, `env`, `printenv`, `op read`, `vault kv get`,
   `security find-generic-password -w` on their own line, `aws secretsmanager get-secret-value`.
2. **Never ask the user to paste a secret into chat.** Ask them to store it
   themselves (secret manager UI, hidden terminal prompt, OS keychain dialog),
   then refer to it by *name*.
3. **Use secrets only through injection:** `<tool> run -- <command>` style
   wrappers, `$(...)` substitution *inside* the command that consumes it,
   stdin pipes, or a credential-injecting proxy. The agent may compose the
   command; it must not see the output of the lookup.
4. **Never write secret values into files the agent created**, into git, into
   MCP/agent config files, or into URLs/query strings.
5. If a secret appears in output by accident: stop, tell the user which
   secret was exposed and where, and recommend **rotating it**. Do not repeat it.
6. Prefer, in order: **no secret at all (OIDC/workload identity)** >
   **proxy/broker injection** > **runtime env injection from a manager** >
   **encrypted file decrypted at runtime** > plaintext `.env` (last resort,
   git-ignored, agent read-denied).

---

## 1. Decision guide

| Situation | Best pattern | Go to |
|---|---|---|
| CI/CD or cloud workload talking to AWS/GCP/Azure | Keyless OIDC / workload identity | §2.5 |
| AI agent must call an HTTP API | Credential-injecting proxy | §2.3 |
| Local dev / scripts need env vars | Secret manager + `run --` injection | §2.1 |
| Signing, decryption, SSH, GPG | Key stays in agent/HSM/KMS; call by handle | §2.4 |
| Secrets must live in the repo (GitOps) | SOPS / sealed-secrets, decrypt at runtime | §2.1 |
| Preventing accidental print/log | Opaque types + redaction + scanning | §2.2, §2.6 |
| Sensitive *data* (PII, card numbers) | Tokenization / enclaves | §2.7 |

---

## 2. Patterns

### 2.1 Runtime injection (env vars + secret manager)

Code knows only the variable **name**. A launcher fetches the value and
injects it into the child process environment.

```python
import os
token = os.environ["API_TOKEN"]   # code uses it; nobody typed or saw it
```

**Battle-tested launchers:**

```bash
# 1Password CLI: .env holds references like API_TOKEN="op://Private/GitHub/token"
op run --env-file=.env -- python app.py
op inject -i config.tpl.yaml -o config.yaml      # templated file (git-ignore output)

# Doppler
doppler run -- python app.py

# Infisical
infisical run -- python app.py

# HashiCorp Vault (avoid `vault kv get` to stdout)
envconsul -secret="secret/myapp" python app.py   # or Vault Agent templates

# AWS credentials from OS keychain, short-lived STS session
aws-vault exec prod -- python app.py

# SOPS: encrypted file in git, decrypted only into the child env
sops exec-env secrets.enc.yaml 'python app.py'

# Bitwarden Secrets Manager
bws run -- python app.py
```

**OS keychain, no third-party service:**

```bash
# macOS: user stores it (prompts for value, nothing echoed)
security add-generic-password -a "$USER" -s my-api-token -w
# use it: lookup happens inside the command; agent never sees output
API_TOKEN="$(security find-generic-password -a "$USER" -s my-api-token -w)" python app.py

# Linux (libsecret)
secret-tool store --label="my api token" service my-api-token    # prompts
API_TOKEN="$(secret-tool lookup service my-api-token)" python app.py

# Any shell: let the *user* enter it hidden, in their own terminal
read -rs API_TOKEN && export API_TOKEN
```

Caveat: env vars are visible to the process and its children (and to
`/proc/<pid>/environ` for the same user). For higher assurance pass via
stdin or file descriptor, or use a proxy (§2.3).

### 2.2 Opaque wrapper types (stop accidental exposure in code)

```python
from pydantic import SecretStr
class Settings(BaseModel):
    api_token: SecretStr
s = Settings(api_token=os.environ["API_TOKEN"])
print(s)                          # api_token=SecretStr('**********')
requests.get(url, headers={"Authorization": f"Bearer {s.api_token.get_secret_value()}"})
```

```rust
use secrecy::{SecretString, ExposeSecret};
let token = SecretString::from(std::env::var("API_TOKEN")?);
// Debug prints [REDACTED]; access is explicit and greppable:
client.bearer_auth(token.expose_secret());
```

Other ecosystems: Go: wrap in a struct implementing `String()`/`GoString()`
→ `"[REDACTED]"`; Java/Kotlin: `char[]` + overridden `toString`; Node: keep
in a closure/class with a custom `toJSON`/`util.inspect.custom`.

**Log redaction filter (Python):**

```python
import logging, os, re
SECRETS = [v for k, v in os.environ.items() if k.endswith(("_TOKEN", "_KEY", "_SECRET")) and v]
class Redact(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        for s in SECRETS:
            msg = msg.replace(s, "[REDACTED]")
        record.msg, record.args = msg, ()
        return True
logging.getLogger().addFilter(Redact())
```

**CI masking:** GitHub Actions masks `${{ secrets.* }}` automatically; mask
derived values with `echo "::add-mask::$VALUE"`. GitLab: "Masked" variables.

### 2.3 Credential-injecting proxy / broker (best for AI agents)

The program or agent calls a local endpoint **without** a credential (or with
a fake placeholder). The proxy, which alone can read the vault, attaches the
real `Authorization` header on egress and returns only the response.

```
agent ──(no key / fake key)──► local proxy ──(real key injected)──► api.example.com
                                    ▲
                           OS keychain / vault
```

Why it's strongest: prompt injection cannot extract a value that never enters
the context window. Add host/method/path allow-lists and response redaction
(in case the API echoes the key).

Limit: it protects the **credential**, not the **access**. A hijacked agent
can still *use* the proxy while it runs. Pair with least-privilege scopes,
allow-lists, short TTLs and sandboxing.

Minimal illustration (for understanding; use a maintained tool in practice):

```python
# tiny_inject_proxy.py: forwards localhost:8787/* to UPSTREAM with injected header
import os, http.server, urllib.request
UPSTREAM = "https://api.example.com"
TOKEN = os.environ["API_TOKEN"]            # launched via `op run -- python tiny_inject_proxy.py`
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        req = urllib.request.Request(UPSTREAM + self.path,
                                     headers={"Authorization": f"Bearer {TOKEN}"})
        with urllib.request.urlopen(req) as r:
            body = r.read().replace(TOKEN.encode(), b"[REDACTED]")
            self.send_response(r.status); self.end_headers(); self.wfile.write(body)
http.server.HTTPServer(("127.0.0.1", 8787), H).serve_forever()
```

The agent is told only: "call `http://127.0.0.1:8787/...`".

The same idea in production: **API gateways / sidecars** (Envoy, Kong,
NGINX `proxy_set_header`), **service meshes**, and **MCP servers that hold
the credential server-side** and expose only actions.

### 2.4 Keys that never leave secure hardware (use by handle)

Ask a component to *perform the operation*; never extract the key.

```bash
# SSH: private key held by agent; programs request signatures
ssh-add ~/.ssh/id_ed25519          # or 1Password / Secretive (Secure Enclave) SSH agent
git commit -S ...                   # gpg-agent / ssh signing

# Cloud KMS: sign/decrypt server-side, key material never exported
aws kms sign --key-id alias/release-signing --message fileb://digest.bin \
  --message-type DIGEST --signing-algorithm ECDSA_SHA_256
gcloud kms asymmetric-sign --key k --keyring r --location global --version 1 \
  --digest-algorithm sha256 --input-file data --signature-file data.sig

# Envelope encryption: KMS wraps a data key; plaintext data key lives only in memory
```

Hardware options: **HSMs** (AWS CloudHSM, Azure Managed HSM, Thales, Entrust),
**TPM 2.0**, **Apple Secure Enclave**, **YubiKey / PIV / FIDO2**.

### 2.5 Eliminate long-lived secrets (keyless / OIDC / workload identity)

The platform proves *who the workload is* and exchanges that for a
short-lived, scoped token. There is nothing static to leak.

```yaml
# GitHub Actions → AWS, no stored keys
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::123456789012:role/deploy
      aws-region: us-east-1
```

Equivalents: GCP **Workload Identity Federation**, Azure **Workload
Identity / Managed Identity**, Kubernetes **projected service-account
tokens** + IRSA / GKE WI, **SPIFFE/SPIRE** for service-to-service identity,
**Vault dynamic secrets** (DB creds minted per-lease, auto-revoked),
**Sigstore keyless signing** (cosign) for artifacts.

### 2.6 Detect and prevent leaks

```bash
# pre-commit secret scanning
gitleaks git --staged        # or `gitleaks protect --staged` on older versions
trufflehog git file://. --only-verified
detect-secrets scan > .secrets.baseline
```

Also: enable **GitHub secret scanning + push protection**; keep `.env*` in
`.gitignore`; never put tokens in URLs (they land in proxy/server logs);
rotate immediately on any exposure.

### 2.7 Sensitive *data* (not credentials)

- **Tokenization / vaulting:** replace PANs/SSNs/PII with tokens; only a
  vault service detokenizes (e.g. Skyflow, VGS, Basis Theory, Stripe's
  tokenization for cards).
- **Format-preserving encryption / field-level encryption:** MongoDB
  Queryable Encryption, AWS DynamoDB client-side encryption, Google Tink.
- **Confidential computing:** AWS Nitro Enclaves, Azure Confidential VMs,
  GCP Confidential VMs, Intel SGX/TDX, AMD SEV-SNP: process data the host
  operator cannot inspect.
- **Research-grade:** homomorphic encryption (Microsoft SEAL, OpenFHE),
  secure multi-party computation.

---

## 3. AI-agent-specific setup (Claude Code, Cursor, Codex, etc.)

### 3.1 Block the agent from reading secret files

Claude Code `.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)",
      "Read(~/.aws/credentials)",
      "Read(~/.ssh/**)"
    ]
  }
}
```

Cursor: `.cursorignore`. Others: equivalent ignore/deny lists. Also keep
real tokens **out of `mcp.json` / agent config**: use env references or a
proxy command instead.

### 3.2 Give the agent capabilities, not credentials

- Wrap credentialed actions as **tools/MCP servers** that hold the key
  server-side and return results only.
- Or run the agent's commands through `op run` / `doppler run` / a
  credential proxy so it composes commands but never sees values.
- Scope every token to the minimum (read-only where possible, single repo,
  short TTL); prefer per-agent tokens so you can revoke one without the rest.
- Require human approval for destructive or credential-management actions.

### 3.3 Workflow for "the agent needs a new secret"

1. Agent tells the user the secret **name** and where to store it
   (e.g. "add `STRIPE_KEY` to 1Password Environment `myapp-dev`" or
   "run `security add-generic-password -a $USER -s stripe-key -w` in your terminal").
2. User stores it; agent never sees it.
3. Agent references it via injection (`op run --`, proxy, `$(lookup)` inline).
4. Agent verifies by **behavior** (HTTP 200, test passes), never by printing.

---

## 4. Reference: existing solutions

### 4.1 Battle-tested (mature, widely deployed)

| Category | Solutions |
|---|---|
| Secret managers | HashiCorp Vault / OpenBao, AWS Secrets Manager & SSM Parameter Store, GCP Secret Manager, Azure Key Vault, 1Password (CLI `op`, Secrets Automation), Doppler, Infisical, Bitwarden Secrets Manager, CyberArk Conjur, Akeyless, Keeper Secrets Manager |
| Encrypted-in-repo | Mozilla/CNCF **SOPS** (+ age/KMS), Bitnami **Sealed Secrets**, **External Secrets Operator** (K8s), git-crypt |
| Local credential helpers | **aws-vault**, macOS Keychain (`security`), libsecret (`secret-tool`), Windows Credential Manager, `pass`, git credential helpers |
| Keys by handle | ssh-agent, gpg-agent, AWS/GCP/Azure KMS, CloudHSM, TPM 2.0, Secure Enclave (e.g. Secretive), YubiKey |
| Keyless identity | GitHub/GitLab OIDC, AWS IAM Roles Anywhere / IRSA, GCP Workload Identity Federation, Azure Workload Identity, SPIFFE/SPIRE, Vault dynamic secrets, Sigstore |
| Opaque types | Pydantic `SecretStr`, Rust `secrecy`, Spring/Jackson `@JsonIgnore` patterns |
| Leak detection | gitleaks, TruffleHog, detect-secrets, GitHub secret scanning + push protection |
| Gateways / injection | Envoy, Kong, NGINX, Istio/Linkerd (mTLS + header injection) |

### 4.2 AI-agent-specific (2026; newer, verify before production use)

| Tool | Type | What it does | Link |
|---|---|---|---|
| **1Password Environments MCP / agent hooks** | Official MCP + hooks | Agent manages env var *names*; values injected at runtime; per-action auth prompt; .env validation hooks for Cursor, Copilot, Claude Code, Windsurf | https://www.1password.dev/get-started/secure-ai-access · https://www.1password.dev/environments/mcp-codex-server |
| **1Password Agentic Autofill** | Official (early access) | Logs agents into websites; user approves; agent never sees password | https://1password.dev/get-started/secure-ai-access |
| **Keeper Agent Kit** | Official skills (Claude Plugin Marketplace) | Skills teaching agents to inject secrets via `ksm exec` without showing them in chat; RBAC + audit | https://docs.keeper.io/en/keeperpam/secrets-manager/integrations/ai-agents |
| **agentgateway** (Agentic AI Foundation) | Gateway | Just-in-time credential injection on egress for MCP and API calls; OAuth on-behalf-of exchange | https://agentgateway.dev/blog/2026-07-27-credential-injection-ai-agent-egress-cb4a/ |
| **Composio** (Proxy Execute) | Hosted broker | Server-side credential decryption and injection, policy enforcement before the call | https://composio.dev/blog/credential-isolation-ai-agents |
| **hoop.dev** | Access gateway | Proxies agent access, isolates credentials, masks sensitive fields, session recording | https://hoop.dev/blog/how-to-implement-secrets-management-for-claude-skills/ |
| **Cloak** (hoophq) | Local proxy (OSS) | Gives agent fake DSN/API key; swaps real one on egress from OS keychain; Claude Code support | https://github.com/hoophq/cloak |
| **AgentVault** | Local vault + MCP proxy (OSS) | Encrypted vault, header injection, host/method/path policies, hash-chained audit log | https://github.com/danielou1208/agent_vault |
| **AgentSecrets** | Proxy + CLI (OSS) | Keychain-backed injection; redacts credentials echoed in API responses | https://pkg.go.dev/github.com/The-17/agentsecrets |
| **blind-vault** | Claude Code skill (OSS, macOS) | Native dialog → Keychain; `vault use <name> -- cmd`; no "get" command by design | https://github.com/AnYejun/blind-vault |
| **secure-vault-mcp** | MCP server (OSS) | AES-256-GCM store, short-lived scoped tokens, server-side injection | https://claudemarketplaces.com/mcp/io.github.mdfifty50-boop/secure-vault |
| **mcp-1password** (kefapps) | MCP server (OSS) | 1Password access, opaque-by-default secret handling | https://github.com/kefapps/onepassword-mcp-codex |
| **21st.dev credential vaults** | Hosted TLS-intercepting proxy | Keys pinned to agents, injected at the edge | https://21st.dev/community/blog/credential-vaults |

Further reading: 1Password's position on not exposing raw credentials over
MCP: https://1password.com/blog/where-mcp-fits-and-where-it-doesnt

> Community projects above are young. Read the code, check the threat
> model, and test with a throwaway key before trusting them with real ones.

---

## 5. Quick-start recipes

**Solo dev, Claude Code, macOS:**
store keys in Keychain or 1Password → `Read(./.env)` deny rule →
run tools via `op run --` or Cloak → gitleaks pre-commit hook.

**Team using 1Password or Keeper already:**
use their official agent integrations (§4.2) → per-project Environments/
vaults → least-privilege service accounts per agent.

**CI/CD:**
OIDC to the cloud (no stored keys) → remaining third-party tokens in the CI
secret store, masked → secret scanning + push protection on the repo.

**Production agents / multi-tenant:**
gateway/broker (agentgateway, Composio, hoop.dev, or Envoy/Kong you run) →
policy allow-lists → short-lived tokens or OAuth on-behalf-of → audit logs →
human approval for high-impact actions.

---

## 6. Checklist

- [ ] No secret values in code, git, chat, agent config, URLs, or logs
- [ ] Secrets stored in a manager/keychain; referenced by name
- [ ] Injected at runtime (`run --`, proxy, KMS handle, OIDC)
- [ ] Opaque types + log redaction in the codebase
- [ ] Agent read-deny rules for `.env*`, credential dirs
- [ ] Least privilege + short TTL + per-agent tokens
- [ ] Secret scanning in pre-commit and on the remote
- [ ] Audit logging on the secret store; rotation plan; rotate on any exposure