# Control Flow: US-008 - Plugin Registration via Manifest

## Success Path (Happy Path)

```
[Developer Creates Plugin Directory and Files]
     |
     v
+-----------------------------------------------------------------+
| Step 1: Plugin Discovery                                         |
| ---------------------------------------------------------------- |
| Trigger: Platform startup scan OR file watcher event             |
| Action: Scan plugins/ directory for subdirectories               |
| Look for: plugins/<name>/plugin.json in each subdirectory        |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 2: Manifest Validation                                      |
| ---------------------------------------------------------------- |
| Input: plugin.json content                                       |
| Validation:                                                       |
|   - Valid JSON syntax                                             |
|   - Required fields: manifest_version, name, version, type       |
|   - type in [tool, mcp, skill, endpoint]                         |
|   - capabilities.tools[] names follow naming convention           |
|   - No tool name conflicts with existing registered plugins      |
| Output: Validated PluginManifest object                           |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 3: Plugin Registration                                      |
| ---------------------------------------------------------------- |
| Action: Create Plugin record in database                         |
| Status: "needs_config" if config_schema defined,                 |
|   "ready" if no config needed                                     |
| Log: "INFO: Plugin '{name}' registered (type={type})"           |
+-----------------------------------------------------------------+
     |
     v (if config needed)
+-----------------------------------------------------------------+
| Step 4: Plugin Configuration                                     |
| ---------------------------------------------------------------- |
| Trigger: Operator submits config via API or admin UI             |
| Validation: Config values match config_schema (JSON Schema)      |
| Secrets: Secret fields encrypted with Fernet before storage      |
| Connectivity: Test external connections (e.g., DB ping, API test)|
| Status: "configured"                                              |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 5: Plugin Activation                                        |
| ---------------------------------------------------------------- |
| Trigger: Operator clicks "Activate" or calls API                 |
| For MCP type: Verify server command exists and starts             |
| For Tool type: Import Python module, verify tool functions        |
| For Skill type: Verify SKILL.md file exists and is readable      |
| Status: "activated" (added to active plugin set)                  |
| Log: "INFO: Plugin '{name}' activated"                           |
| Event: "plugin_changed" emitted (invalidates pre-warm pool)      |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 6: Available in New Sessions                                |
| ---------------------------------------------------------------- |
| OptionsBuilder includes plugin's mcp_servers/tools/skills        |
| New sessions: include activated plugin capabilities               |
| Active sessions: unaffected (continue with original config)       |
+-----------------------------------------------------------------+
     |
     v
[Plugin Tools Available to Users in New Sessions]
```

## Edge Case Branches

### EC-055: Invalid JSON Syntax (Step 2)

```
+-----------------------------------------------------------------+
| Trigger: plugin.json fails JSON parse                            |
| ---------------------------------------------------------------- |
| Error: {                                                          |
|   plugin: "slack-notify",                                         |
|   error: "Invalid JSON",                                          |
|   detail: "Line 12: Expected comma after 'version' field.       |
|   Add a comma before the 'type' field.",                         |
|   file: "plugins/slack-notify/plugin.json"                       |
| }                                                                 |
| Status: "errored"                                                |
| Recovery: Developer fixes JSON, file watcher re-triggers         |
|   discovery                                                       |
+-----------------------------------------------------------------+
```

### EC-056: Tool Name Conflicts with Built-in (Step 2)

```
+-----------------------------------------------------------------+
| Trigger: Plugin declares tool name "Bash" or "Read"              |
| ---------------------------------------------------------------- |
| Error: "Tool name 'Bash' is reserved (built-in SDK tool).       |
|   Plugin tools must use namespace: mcp__<plugin>__<tool>"        |
| Status: "errored"                                                |
| Recovery: Developer renames tool with proper namespace            |
+-----------------------------------------------------------------+
```

### EC-059: Tool Name Conflicts with Another Plugin (Step 2)

```
+-----------------------------------------------------------------+
| Trigger: Plugin B declares tool "mcp__slack__send_message" but   |
|   Plugin A already registered that tool name                      |
| ---------------------------------------------------------------- |
| Error: "Tool name 'mcp__slack__send_message' already             |
|   registered by plugin 'slack-v1'. Use a unique tool name."      |
| Status: "errored"                                                |
| Recovery: Developer changes tool name in manifest                |
+-----------------------------------------------------------------+
```

### EC-058: MCP Server Command Not Found (Step 5)

```
+-----------------------------------------------------------------+
| Trigger: Plugin declares stdio MCP server with command that      |
|   does not exist on the system                                    |
| ---------------------------------------------------------------- |
| Action: Attempt to start MCP server subprocess                   |
| Timeout: 10 seconds                                              |
| Error: "MCP server 'npx @my/server' failed to start:            |
|   command not found. Ensure the command is installed."            |
| Status: "errored"                                                |
| Stderr: Captured and available via admin API                     |
| Recovery: Operator installs missing command, retries activation  |
+-----------------------------------------------------------------+
```

### EC-060: Plugin Activated While Sessions Active (Step 5)

```
+-----------------------------------------------------------------+
| Trigger: Operator activates plugin while 3 sessions are active   |
| ---------------------------------------------------------------- |
| Action: Plugin added to active set for NEW sessions only         |
| Active sessions: continue with original plugin set               |
| Notification to active sessions:                                  |
|   {type: "plugin_update",                                         |
|    message: "New tools available. Restart session to access."}   |
| Pre-warm pool: invalidated (new slots use updated config)        |
+-----------------------------------------------------------------+
```

### EC-064: SKILL.md File Deleted (Step 5, post-activation)

```
+-----------------------------------------------------------------+
| Trigger: File watcher detects SKILL.md deletion                  |
| ---------------------------------------------------------------- |
| Action: Plugin status set to "degraded"                          |
| Active sessions that loaded skill: continue working (cached)     |
| New sessions: skill unavailable                                   |
| Operator notification: "Plugin '{name}' degraded: SKILL.md       |
|   file not found. Restore the file or deactivate the plugin."   |
+-----------------------------------------------------------------+
```

### EC-067: Plugin Secret Invalid Mid-Session (Post-activation)

```
+-----------------------------------------------------------------+
| Trigger: 3 consecutive auth failures from same plugin in 60s     |
| ---------------------------------------------------------------- |
| Action: Plugin status set to "auth_failed"                       |
| Active sessions: tool invocations show auth error                |
| Operator notification: "Plugin '{name}' auth failed. API key     |
|   may be expired. Update credentials."                           |
| Allow: Secret update without deactivating plugin                 |
| After update: Plugin status returns to "activated"               |
+-----------------------------------------------------------------+
```

### EC-071: Secret Key Rotated (Post-activation)

```
+-----------------------------------------------------------------+
| Trigger: Platform SECRET_KEY changed, secrets cannot decrypt     |
| ---------------------------------------------------------------- |
| Detection: On startup, attempt to decrypt all secrets            |
| If decryption fails: Plugin blocked from activation              |
| Admin notification: "N plugins require secret re-encryption.     |
|   Run: python -m claude_sdk_pattern.tools.reencrypt_secrets"     |
| Utility: Prompts for old key, decrypts, re-encrypts with new    |
+-----------------------------------------------------------------+
```

## Flow Summary Table

| Step | Success Outcome | Edge Cases | Design Decision |
|------|-----------------|------------|-----------------|
| 1 | Plugin directory found | None | Scan on startup + file watcher |
| 2 | Manifest valid | EC-055, EC-056, EC-059 | Line-number errors, namespace enforcement |
| 3 | Plugin registered | None | DB persistence |
| 4 | Plugin configured | EC-071 (key rotation) | Encrypted storage, connectivity test |
| 5 | Plugin activated | EC-058, EC-060, EC-064, EC-067 | Test before activate, new-sessions-only |
| 6 | Available to users | None | OptionsBuilder merge |

---

*End of Control Flow: US-008*
