# PagerDuty SLA Requirements - Cheat Sheet

## 📊 SLA Response Times by Severity and Support Plan

### Response Time Matrix

| Severity | Premium Support | Advanced Support | Basic Support |
|----------|----------------|------------------|---------------|
| **Sev 1** | 1 hour | 1 hour | 1 hour |
| **Sev 2** | 2 hours | 4 hours | None |
| **Sev 3** | 4 hours | 8 hours | None |
| **Sev 4** | None | None | None |

> **Note**: Response times apply to both L2 (Support Team via ServiceNow) and L3 (SLZ Team via GitHub)

---

## ⏱️ Update Frequency Requirements

Update frequency matches the response time requirements:

| Severity | Premium Support | Advanced Support | Basic Support |
|----------|----------------|------------------|---------------|
| **Sev 1** | Every 1 hour | Every 1 hour | Every 1 hour |
| **Sev 2** | Every 2 hours | Every 4 hours | N/A |
| **Sev 3** | Every 4 hours | Every 8 hours | N/A |
| **Sev 4** | N/A | N/A | N/A |

---

## 🚨 Critical Timelines for On-Call

### PagerDuty Acknowledgment
```
⏰ ACKNOWLEDGE WITHIN: 15 minutes
⚠️  If not acknowledged: Escalates to 2nd responder
⏳ Acknowledgment expires: After 60 minutes if not resolved
```

### Initial Response to Customer
```
⏰ INITIAL RESPONSE: Within 30 minutes of acknowledging
📝 Post in GitHub issue with @support tag
✅ Confirms we're investigating
```

---

## 📋 SLA Countdown Timer

### Sev 1 - Premium/Advanced Support

```
┌─────────────────────────────────────┐
│  ALERT RECEIVED                     │
│  ↓ 15 min                          │
│  ACKNOWLEDGE                        │
│  ↓ 30 min                          │
│  INITIAL RESPONSE (@support)        │
│  ↓ 30 min (Total: 1 hour)         │
│  ⚠️  SLA DEADLINE                   │
│  ↓ 1 hour                          │
│  STATUS UPDATE 1                    │
│  ↓ 1 hour                          │
│  STATUS UPDATE 2                    │
│  ↓ Continue every hour             │
└─────────────────────────────────────┘
```

### Sev 2 - Premium Support

```
┌─────────────────────────────────────┐
│  ALERT RECEIVED                     │
│  ↓ 15 min                          │
│  ACKNOWLEDGE                        │
│  ↓ 30 min                          │
│  INITIAL RESPONSE (@support)        │
│  ↓ 1.5 hours (Total: 2 hours)     │
│  ⚠️  SLA DEADLINE                   │
│  ↓ 2 hours                         │
│  STATUS UPDATE 1                    │
│  ↓ 2 hours                         │
│  STATUS UPDATE 2                    │
└─────────────────────────────────────┘
```

### Sev 2 - Advanced Support

```
┌─────────────────────────────────────┐
│  ALERT RECEIVED                     │
│  ↓ 15 min                          │
│  ACKNOWLEDGE                        │
│  ↓ 30 min                          │
│  INITIAL RESPONSE (@support)        │
│  ↓ 3.5 hours (Total: 4 hours)     │
│  ⚠️  SLA DEADLINE                   │
│  ↓ 4 hours                         │
│  STATUS UPDATE 1                    │
│  ↓ 4 hours                         │
│  STATUS UPDATE 2                    │
└─────────────────────────────────────┘
```

---

## 🎯 SLA Compliance Checklist

### For Every Incident

- [ ] **T+0**: Alert received
- [ ] **T+15 min**: Acknowledged in PagerDuty
- [ ] **T+30 min**: Initial response posted with `@support`
- [ ] **T+SLA**: First substantial update provided
- [ ] **Ongoing**: Regular updates per severity schedule
- [ ] **Resolution**: Solution documented with `@support`
- [ ] **Closure**: PagerDuty incident resolved after case closed

---

## 📱 Setting Up SLA Reminders

### Recommended Approach

1. **When you acknowledge an incident**, immediately set timers:
   - **Sev 1**: Set alarm for 45 minutes (15 min buffer before 1-hour SLA)
   - **Sev 2 Premium**: Set alarm for 1.5 hours (30 min buffer before 2-hour SLA)
   - **Sev 2 Advanced**: Set alarm for 3.5 hours (30 min buffer before 4-hour SLA)

2. **After initial response**, set recurring reminders:
   - **Sev 1**: Every 50 minutes (10 min buffer before hourly updates)
   - **Sev 2 Premium**: Every 1 hour 50 minutes
   - **Sev 2 Advanced**: Every 3 hours 50 minutes

### Phone Timer Examples

**Sev 1 Incident**:
```
Timer 1: "Initial Response" - 30 minutes
Timer 2: "SLA Deadline" - 45 minutes
Timer 3: "Status Update" - 1 hour 50 minutes
```

**Sev 2 Premium Incident**:
```
Timer 1: "Initial Response" - 30 minutes
Timer 2: "SLA Deadline" - 1 hour 30 minutes
Timer 3: "Status Update" - 3 hours 50 minutes
```

---

## ⚠️ SLA Risk Indicators

### Yellow Flags (Take Action Soon)
- ⚠️  50% of SLA time elapsed without substantial progress
- ⚠️  Missing required information from customer
- ⚠️  Waiting on another team's response
- ⚠️  Complex issue requiring deep investigation

**Action**: Provide proactive status update, consider adding responder

### Red Flags (Immediate Action Required)
- 🚨 75% of SLA time elapsed
- 🚨 No clear path to resolution
- 🚨 Blocked by external dependency
- 🚨 Multiple incidents competing for attention

**Action**: Add responder immediately, escalate to management if needed

---

## 🔄 SLA During Handoffs

### Outgoing On-Call Responsibilities
- Document time remaining until next SLA deadline
- Clearly state what's been done and what's pending
- Ensure incoming on-call has all context
- Remain available for questions during transition

### Incoming On-Call Responsibilities
- Review all open incidents immediately
- Check time remaining for each SLA
- Prioritize based on urgency
- Acknowledge understanding of handoff

---

## 📊 SLA Tracking Template

Use this template to track multiple incidents:

```
┌──────────────────────────────────────────────────────────┐
│ Case: CS_______ │ Sev: ___ │ Plan: ________              │
│ Acknowledged: __:__ │ Initial Response: __:__            │
│ Next Update Due: __:__ │ SLA Deadline: __:__             │
│ Status: ___________________________________________       │
└──────────────────────────────────────────────────────────┘
```

**Example**:
```
┌──────────────────────────────────────────────────────────┐
│ Case: CS4128655 │ Sev: 1 │ Plan: Premium                 │
│ Acknowledged: 09:15 │ Initial Response: 09:30            │
│ Next Update Due: 10:30 │ SLA Deadline: 10:15             │
│ Status: Investigating VPC provisioning timeout            │
└──────────────────────────────────────────────────────────┘
```

---

## 🎯 SLA Best Practices

### DO ✅
- Set multiple reminders/alarms
- Provide updates even if no progress (transparency)
- Escalate proactively when approaching deadline
- Document all actions with timestamps
- Over-communicate rather than under-communicate
- Use templates for consistent messaging
- Track multiple incidents in a spreadsheet/notes

### DON'T ❌
- Rely on memory for SLA deadlines
- Wait until last minute to provide updates
- Assume silence is acceptable
- Skip updates because "nothing has changed"
- Forget to account for time zones
- Let incidents go unacknowledged
- Miss deadlines without escalating

---

## 🌍 Time Zone Considerations

### Customer Time Zones
- Customers may be in different time zones
- SLA clock runs 24/7 regardless of time zones
- Night/weekend incidents still have same SLA requirements
- Consider customer business hours for non-urgent communications

### Team Coverage
- Ensure handoffs account for time zones
- Document clearly when handing off across regions
- Set expectations for response times during off-hours

---

## 📈 SLA Metrics to Track

### Individual Performance
- Average acknowledgment time
- Average initial response time
- SLA compliance rate
- Number of escalations
- Average resolution time

### Team Performance
- Overall SLA compliance
- Incidents by severity
- Common SLA miss reasons
- Escalation patterns
- Customer satisfaction scores

---

## 🆘 What to Do When SLA is at Risk

### 30 Minutes Before Deadline

1. **Assess situation**:
   - Can you meet the deadline?
   - What's blocking progress?
   - Do you need help?

2. **Take action**:
   - Add responder if needed
   - Escalate to service team if applicable
   - Provide proactive status update

3. **Communicate**:
   ```markdown
   @support Status update:
   We are actively investigating this issue. Current findings:
   - [WHAT YOU KNOW]
   - [WHAT YOU'RE DOING]
   
   We are working to provide a resolution and will update within [TIME].
   ```

### If SLA is Missed

1. **Don't panic** - focus on resolution
2. **Provide immediate update** explaining situation
3. **Escalate to management** for awareness
4. **Document** what caused the miss
5. **Continue working** toward resolution
6. **Learn** from the incident for future improvement

---

## 📞 Emergency Contacts

When you need help meeting SLA:

| Situation | Contact | Method |
|-----------|---------|--------|
| Need SLZ team help | Add Responder | PagerDuty |
| Service team issue | Service team | Slack + GitHub |
| Multiple Sev 1s | Team lead | Phone + Slack |
| Customer escalation | Management | Immediate notification |
| SLA at risk | Add Responder | PagerDuty + Slack |

---

## 🔔 SLA Reminder Script

Copy this to your notes app for quick reference:

```
INCIDENT RECEIVED
├─ [  ] Acknowledge (15 min)
├─ [  ] Initial Response (30 min)
├─ [  ] Check Support Plan
├─ [  ] Calculate SLA Deadline
├─ [  ] Set Reminders
└─ [  ] Begin Investigation

SLA DEADLINE APPROACHING
├─ [  ] Assess Progress
├─ [  ] Add Responder if Needed
├─ [  ] Provide Status Update
└─ [  ] Escalate if Required

RESOLUTION
├─ [  ] Document Solution
├─ [  ] Wait for Case Closure
├─ [  ] Resolve PagerDuty
└─ [  ] Close GitHub Issue
```

---

**Pro Tip**: Keep this cheat sheet open on a second monitor during your on-call shift!

**Last Updated**: 2026-02-19