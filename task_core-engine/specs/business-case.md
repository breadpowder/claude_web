# Business Case: claude_sdk_pattern Core Engine

> **Document Version**: 1.0
> **Date**: 2026-02-07
> **Status**: Draft - Pending Review

---

## 1. Problem Statement

Organizations that have adopted the Claude Agent SDK for development workflows face a gap: the SDK provides powerful agent capabilities (MCP tools, custom tools, skills, subagents) but no production path to share these capabilities with non-developer team members. Today, each developer runs the SDK locally via CLI. There is no shared web interface, no cost controls, no audit logging, and no way for non-technical users to benefit from the tools developers have built.

The result: developer-built AI workflows remain siloed, teams duplicate effort building bespoke web wrappers, and organizations cannot adopt Claude Agent capabilities at team scale due to missing operational controls (RBAC, cost caps, observability).

---

## 2. Market Opportunity

### 2.1 Target Segment

**Primary**: Self-hosted teams of 5-50 people who are committed to the Claude ecosystem and have already invested in building MCP servers or custom tools for the Claude Agent SDK.

**Secondary**: Enterprise teams (50-200 people) with compliance requirements (HIPAA, SOC2, data residency) that prevent use of SaaS AI platforms.

### 2.2 Market Signals

| Signal | Evidence |
|--------|----------|
| Demand for Claude Agent SDK web platform | GitHub issue anthropics/claude-agent-sdk-python#412: 40+ users requesting web platform support |
| Demand for faster startup | GitHub issue anthropics/claude-agent-sdk-python#333: 60+ upvotes on cold start performance |
| Enterprise AI adoption blocked by security | 60% of companies block public AI tools (Gartner 2024 survey) |
| Context switching productivity loss | 40% productivity gain when tool count drops from 5 to 1 (internal survey) |

### 2.3 Competitive Landscape

| Alternative | Gap This Platform Fills |
|-------------|------------------------|
| ChatGPT / Claude.ai | Cannot access private company data; no self-hosted option; no custom MCP tools |
| OpenWebUI | No Claude Agent SDK subprocess management; LangChain abstraction lags SDK by 6 months |
| Dify | Workflow-centric not chat-centric; no SDK-native integration |
| Raw SDK | No frontend, no auth, no observability, no deployment; 3-6 months to production |
| LobeChat | No subprocess lifecycle management; UI-focused plugin model |

---

## 3. Value Proposition

### 3.1 For Plugin Developers (Alex)

**Current Pain**: "I built MCP servers for Claude Code CLI, but I cannot share them with my team."

**Value Delivered**: Register existing MCP servers via JSON manifest. Zero rewrite. Team members use them via web browser within 30 minutes.

**Metric**: Time to first working plugin < 30 minutes (from `docker-compose up` to tool invocation).

### 3.2 For Platform Operators (Morgan)

**Current Pain**: "Agent services crash from memory leaks, and I get paged at 3am."

**Value Delivered**: Pre-warming pool eliminates cold start UX issues. RSS monitoring prevents OOM crashes. Prometheus metrics and structured logs provide full observability.

**Metric**: Session crash rate < 0.1%; MTTR < 5 minutes; on-call pages from this service < 1 per month.

### 3.3 For End Users (Jordan)

**Current Pain**: "I switch between 5 apps to get work done, and I lose context between sessions."

**Value Delivered**: Single chat interface with tools that access company data (databases, GitHub, Jira, Slack). Session persistence means no context re-explanation.

**Metric**: Task completion rate > 90%; time to first response < 3 seconds; session abandonment rate < 15%.

### 3.4 For Platform Admins (Sam)

**Current Pain**: "Shadow IT -- developers use unapproved AI tools, and I cannot audit what data is being accessed."

**Value Delivered**: Self-hosted platform with RBAC, per-user cost caps, and audit logging of every tool invocation. Passes compliance review.

**Metric**: Security incidents from AI tools = 0; audit pass rate = 100%; cost per user per month < $50.

---

## 4. Business Value

### 4.1 Developer Productivity

| Without Platform | With Platform | Savings |
|-----------------|---------------|---------|
| Each developer builds bespoke wrapper (80-160 hours) | Deploy platform (4 hours), register plugins (30 min each) | 75-155 hours per developer |
| Non-technical users cannot access agent capabilities | Non-technical users self-serve via chat | Eliminates developer-as-proxy bottleneck |
| Tool integrations siloed per developer | Shared tool catalog across team | Eliminates duplicate integration work |

### 4.2 Cost Control

| Without Platform | With Platform | Savings |
|-----------------|---------------|---------|
| No visibility into per-user API spend | Per-user cost caps and real-time tracking | Prevents $2000+ surprise bills |
| Manual log analysis for cost attribution (weekly lag) | Real-time dashboard with alerts at 80% threshold | Same-day cost visibility |
| One runaway session can exhaust monthly API budget | Session duration limits and per-user caps | Budget predictability within 10% |

### 4.3 Compliance and Security

| Without Platform | With Platform | Benefit |
|-----------------|---------------|---------|
| No audit trail of tool invocations | Full audit log with user, tool, input, result, timestamp | HIPAA/SOC2 compliance |
| API keys scattered across developer machines | Encrypted secret store with rotation support | Reduced credential exposure |
| No access control for agent capabilities | RBAC with least-privilege defaults | Compliance with access control requirements |

---

## 5. Investment Required

### 5.1 Engineering Effort

| Phase | Duration | Team | Cost (at $150/hr) |
|-------|----------|------|-------------------|
| Phase 1: MVP Core Engine | 4 weeks | 1 backend + 1 frontend | ~$48,000 |
| Phase 2: Plugin System | 4 weeks | 1 backend + 1 frontend | ~$48,000 |
| Phase 3: Production Hardening | 4 weeks | 1 backend + 0.5 frontend | ~$36,000 |
| **Total** | **12 weeks** | **2 engineers** | **~$132,000** |

### 5.2 Infrastructure Cost (Per Deployment)

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| Container hosting (16GB, 2 vCPU) | $36-72/month | Supports 2-3 concurrent sessions |
| Database (PostgreSQL - managed) | $15-30/month | Minimal storage requirements |
| Monitoring (Prometheus/Grafana) | $0-50/month | Self-hosted or managed |
| Claude API usage | $50-500/month | Varies by team usage |
| **Total** | **$101-652/month** | Per deployment |

### 5.3 ROI Analysis

**For a team of 10 developers**:

| Item | Annual Value |
|------|-------------|
| Developer time saved (10 devs x 80 hrs x $150/hr) | $120,000 |
| Cost overrun prevention (estimated 2 incidents x $2000) | $4,000 |
| Compliance audit prep time saved (4 audits x 8 hrs x $150/hr) | $4,800 |
| **Total Annual Value** | **$128,800** |
| Investment (engineering + infra year 1) | $140,000 |
| **Payback Period** | **~13 months** |

---

## 6. Risks to Business Case

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Anthropic launches hosted Claude Code (makes self-hosted unnecessary) | Platform becomes less differentiated | 40% | Differentiate on plugin system, compliance controls, and self-hosted data residency |
| No one builds plugins (ecosystem fails) | Platform is just a chat UI (commodity) | 70% | Ship with 5 built-in integrations (GitHub, PostgreSQL, Slack, Jira, filesystem); defer plugin marketplace |
| SDK memory leak worsens or never fixed | Platform requires expensive containers | 30% | Container-per-session architecture already accounts for this; monitor Anthropic fixes |
| Team prefers ChatGPT Teams over self-hosted | No adoption | 20% | Target teams with compliance requirements where ChatGPT is blocked |

---

## 7. Success Criteria for Go/No-Go Decisions

### Phase 1 Exit (Week 4): Continue to Phase 2?

- [ ] Single user can complete a multi-tool task via web browser
- [ ] Pre-warmed session starts in < 3 seconds
- [ ] Session runs for 2+ hours without OOM crash
- [ ] 5+ internal users have tried the platform and provided feedback

### Phase 2 Exit (Week 8): Continue to Phase 3?

- [ ] Plugin developer registers MCP server in < 30 minutes
- [ ] 2+ teams are using the platform weekly
- [ ] Cost tracking shows accurate per-user attribution
- [ ] No security incidents from tool invocations

### Phase 3 Exit (Week 12): Ready for Production?

- [ ] Load test passes (10 concurrent users, 1 hour, < 1% error rate)
- [ ] Grafana dashboard shows all 10 metrics
- [ ] Rolling deployment does not disrupt active sessions
- [ ] Runbook exercise completes within 5 minutes

---

*End of Business Case*
