# PagerDuty Incident Handling - Quick Reference Cheat Sheet

## 🚨 Critical Timelines

| Action | Timeline |
|--------|----------|
| **Acknowledge Alert** | Within 15 minutes |
| **Initial Response** | Within 30 minutes |
| **Sev 1 Updates** | Every 1 hour |
| **Sev 2 Updates** | Every 2-4 hours |

---

## 📋 Step-by-Step Checklist

### ✅ When Alert Arrives (0-15 min)
- [ ] Acknowledge the incident in PagerDuty
- [ ] Note case number, severity, and description
- [ ] Open ServiceNow case
- [ ] Open GitHub issue

### ✅ Initial Assessment (15-30 min)
- [ ] Check Configuration Item (CI)
- [ ] Verify case belongs to SLZ team
- [ ] Review error logs if available
- [ ] Post initial response with `@support` in GitHub

### ✅ Investigation Phase
- [ ] Collect required information (logs, errors, screenshots)
- [ ] Review troubleshooting guide
- [ ] Document findings in GitHub issue
- [ ] Provide regular status updates

### ✅ Resolution Phase
- [ ] Document solution clearly with `@support`
- [ ] Wait for case closure in ServiceNow
- [ ] Resolve PagerDuty incident
- [ ] Close GitHub issue (after ServiceNow closure)

---

## 🎯 Key Actions by Method

### Acknowledge Incident
| Method | Steps |
|--------|-------|
| **Mobile App** | Open app → Tap incident → Tap "Acknowledge" |
| **Website** | Login → Incidents → Click incident → Click "Acknowledge" |
| **Slack** | Click "Acknowledge" button in notification |
| **Email** | Click "Acknowledge" link in email |

### Add Responder
| Method | Steps |
|--------|-------|
| **Website** | Open incident → "Add Responders" → Select person → Add message |
| **Mobile App** | Open incident → "Add Responders" → Select person → Send |

### Resolve Incident
| Method | Steps |
|--------|-------|
| **Website** | Open incident → "Resolve" → Add resolution note |
| **Mobile App** | Open incident → "Resolve" → Add note |
| **Slack** | Click "Resolve" button in notification |

---

## 🔍 Configuration Item Quick Reference

### SLZ Team Owns
```
✅ deploy-arch-ibm-slz-ocp
✅ deploy-arch-ibm-slz-vsi
✅ deploy-arch-ibm-slz-vpc
✅ deploy-arch-ibm-core-security-svcs
✅ deploy-arch-ibm-* (other DAs)
```

### Redirect to Other Teams
| Error Type | Team | Configuration Item |
|------------|------|-------------------|
| Secrets Manager timeout | ACS Security | `secrets-manager` |
| VPC provisioning error | ACS Network | `is` |
| COS bucket error | ACS PAAS Core | `cloud-object-storage` |
| Key Protect error | ACS Security | `kms` |
| IKS/OpenShift error | Container Service | `containers-kubernetes` |

---

## 💬 Communication Templates

### Initial Response (30 min)
```markdown
@support We have received this case and are investigating the issue.
We will provide an update as soon as we have more information about our investigation.

Initial assessment in progress.
```

### Status Update
```markdown
@support Investigation update:
- We have reviewed the logs and identified [WHAT YOU FOUND]
- Currently investigating [WHAT YOU'RE WORKING ON]
- Next steps: [WHAT YOU'LL DO NEXT]

We will provide another update within [TIMEFRAME].
```

### Request Information
```markdown
@support To investigate this issue, we need the following information:
- [LIST MISSING ITEMS]

Could you please ask the customer to provide this/these information?
```

### Provide Solution
```markdown
@support We have identified the issue and the solution:

**Problem**: [CLEAR DESCRIPTION]

**Root Cause**: [WHAT CAUSED IT]

**Solution**: [STEP-BY-STEP]
1. [STEP 1]
2. [STEP 2]
3. [STEP 3]

**Expected Outcome**: [WHAT SHOULD HAPPEN]

The customer can now retry the deployment after applying these changes.
```

### Escalate to Service Team
```markdown
@support This issue is related to [SERVICE] and requires their involvement.

Error details:
- Service: [SERVICE NAME]
- Error: [ERROR MESSAGE]
- Status Code: [IF APPLICABLE]

Could you please:
1. Open a GitHub issue to the [SERVICE] team, OR
2. Update the Configuration Item to [SERVICE CONFIG ITEM]

We will coordinate with the [SERVICE] team to resolve this issue.
```

### Case Reassignment (Slack)
```markdown
Case CS[NUMBER] was assigned to SLZ team but appears to be a [SERVICE] issue.
Error: [BRIEF ERROR DESCRIPTION]
Can @[TEAM] confirm this could be assigned to them?
```

---

## 📊 Required Information Checklist

When investigating, ensure you have:
- [ ] Schematics workspace logs
- [ ] Error messages highlighted
- [ ] Screenshots of errors in IBM Cloud UI
- [ ] Input variables used for deployment
- [ ] IBM Cloud account ID
- [ ] Region where deployment was attempted
- [ ] Timestamp of the failure

---

## 🔗 Essential Links

| Resource | URL |
|----------|-----|
| **PagerDuty** | https://ibm.pagerduty.com |
| **ServiceNow** | https://watson.service-now.com |
| **GitHub Issues** | https://github.ibm.com/GoldenEye/slz-support |
| **Slack - Issues** | #deploy-arch-slz-issues |
| **Slack - Support** | #cloud-support |
| **Slack - Team** | #cpre-team |

### PagerDuty Services
| Severity | Service | Link |
|----------|---------|------|
| **Sev 1** | SLZ Deployable Architectures Sev 1 | https://ibm.pagerduty.com/service-directory/PIONQAB |
| **Sev 2** | SLZ Deployable Architectures Sev 2 | https://ibm.pagerduty.com/service-directory/PAR666J |

---

## ⚠️ Common Mistakes to Avoid

### ❌ DON'T
- Don't communicate directly with customers
- Don't close GitHub issue before ServiceNow case is closed
- Don't miss SLA deadlines
- Don't let incidents go silent
- Don't guess at solutions
- Don't use internal jargon in customer-facing messages
- Don't delay asking for help

### ✅ DO
- Always use `@support` when support team action is needed
- Provide regular updates within SLA timeframes
- Be clear and specific in all communications
- Document all actions in GitHub issues
- Start with log analysis
- Check for known issues first
- Ask for help when needed
- Set reminders for SLA updates

---

## 🆘 When to Escalate

### Add SLZ Responder When:
- You need help from another SLZ team member
- Issue is complex and requires additional expertise
- Approaching SLA deadline and need assistance
- Need to hand off the incident (end of shift)

### Escalate to Service Team When:
- Error is clearly from a specific IBM Cloud service
- Service is experiencing a CIE
- Service API is returning errors
- Issue is beyond DA automation scope

### Escalate to Management When:
- Customer escalation occurs
- Multiple Sev 1 incidents simultaneously
- Unable to meet SLA despite best efforts
- Need additional resources or authority

---

## 📱 Notification Troubleshooting

### Not Receiving Alerts?
1. Check PagerDuty notification preferences
2. Verify mobile app notifications are enabled
3. Check phone's Do Not Disturb settings
4. Test with colleague creating test incident
5. Contact PagerDuty admin

### Cannot Acknowledge?
1. Try different method (app, website, email)
2. Check internet connection
3. Verify you're assigned to the incident
4. Contact another team member to acknowledge for you
5. Report to PagerDuty admin

---

## 🎯 Key Definitions

| Term | Definition |
|------|------------|
| **Case** | ServiceNow case - communication channel with customer |
| **Incident** | PagerDuty incident - alert to on-call person |
| **Issue** | GitHub issue - communication between ACS and SLZ teams |
| **CI** | Configuration Item - identifies the product/service |
| **SLA** | Service Level Agreement - response time requirements |
| **Sev 1** | Severity 1 - Critical production issue |
| **Sev 2** | Severity 2 - Major functionality impaired |

---

## 🔄 Handoff Checklist

When handing off an incident:
- [ ] Document current status in GitHub issue
- [ ] Add incoming on-call as responder
- [ ] Brief them via Slack or phone
- [ ] Transfer ownership in PagerDuty
- [ ] Remain available for questions
- [ ] Share any relevant context or findings

---

**Quick Tip**: Print this cheat sheet and keep it handy during your on-call shift!

**Last Updated**: 2026-02-19