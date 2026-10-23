# Deal Registration Rulebook (v0.2)

This is the policy the triage agent applies to every incoming partner deal registration.
Rules are checked in order and the first rule that produces a REJECT, RETURN or ESCALATE decides the
registration. R11 is a final check that can turn an APPROVE into an ESCALATE.

All dates are evaluated against the program "as of" date returned by the `get_program_context` tool.

## Possible outcomes

| Outcome | Meaning |
|---|---|
| APPROVE | Partner gets registration protection on this account and product for the protection window. |
| REJECT | Registration denied. Partner is told the rule and reason. |
| RETURN | Sent back to the partner to fix missing or invalid information. Not a denial. |
| ESCALATE | A human decides (partner manager plus the account's AE, or sales leadership where noted). |

## Partner roles
Every registration names the partner's role on the deal.
- `Resale`: the partner transacts the deal (the customer buys through the partner).
- `Influence`: the partner shapes the deal (architecture, advisory, implementation) but does not transact it.

One Resale partner and one Influence partner can both hold protection on the same deal. Conflicts (R9, R10) only apply between registrations in the same role.

## R1. Partner eligibility
- The partner must have status `Active`. A `Suspended` or `Terminated` partner is **REJECT**.
- The partner tier must be `Select` or `Premier`. `Registered` tier partners are not eligible for deal registration. **REJECT**.

## R2. Required information and an active opportunity
A registration must include: end customer company name, end customer domain, product, estimated ACV,
expected close date, and a named customer contact.
- Registrations can arrive as free text (a partner email or call notes in `raw_submission`) instead of form fields. Extract the fields from the text. Only treat information as missing if it is truly not there.
- Any of these missing is **RETURN**. A placeholder such as "TBD" is not a named contact.
- An expected close date before the submit date is **RETURN**.
- A registration covers exactly one product. A registration for more than one product is **RETURN**, asking the partner to submit one registration per product. Do not tell the partner which product would conflict.
- The customer must be actively evaluating (an identified need and an engaged customer). If the registration itself shows there is no active evaluation yet, it is **REJECT**. The partner can register again once the opportunity is live.

## R3. Minimum deal size
- Convert the estimated ACV to USD with the program's `fx_rates_to_usd` before applying any threshold in this rulebook.
- Estimated ACV below $10,000 USD is **REJECT**. Small deals go through the standard partner discount, not registration.

## R4. Account match
Match the end customer to a CRM account, using the domain first and the name second.
- One clear match on domain: use that account.
- No match on domain or name: this is a net-new account. Continue (R6 and R7 cannot conflict, and R5 does not apply).
- Uncertain match (the name matches an account but the domain does not, or several accounts are plausible): **ESCALATE**. A human confirms which account this is.
- Check the registration for clues that the customer is part of an existing CRM account, such as an acquisition or a parent company. If the clues point to an existing account, the match is uncertain. **ESCALATE**.

## R5. New business vs. existing customers
- If the account is an existing customer with an active contract, the registration counts as expansion.
- Expansion registrations are allowed only for `Premier` partners. Any other tier is **REJECT**.

## R6. Named strategic accounts
- Accounts flagged `direct_only` (named strategic accounts) cannot be partner-registered without sales leadership approval. **ESCALATE** to sales leadership.

## R7. Public sector
- Accounts in the `Public Sector` segment require a partner with `public_sector_authorized = true`. Otherwise **REJECT**.

## R8. Conflict with the direct sales team
Look at open direct opportunities on the account for the same product.
- Created **more than 30 days** before the registration's submit date and with activity in the last 30 days: the deal is direct-sourced. **REJECT**.
- Created **within 30 days** of the submit date (before or after): a sourcing dispute. **ESCALATE** to the partner manager and the account's AE.
- **No activity for 60 or more days**: stale. It does not block the partner. Continue, and note the stale opportunity in the reasoning so the AE is told.
- Activity between 30 and 60 days ago on an opportunity older than 30 days: not clearly covered. **ESCALATE**.
- Opportunities for a different product do not block.
- The direct team can invite a partner onto its own deal. If the partner says the account's AE asked them to register, **ESCALATE** to that AE to confirm. Do not approve or reject on the partner's word alone.

## R9. First to register (partner vs. partner, same role)
- Another partner holds an `Approved` registration in the same role on the same account and product that has not expired: **REJECT**, unless the next bullet applies.
- Shared contribution: if internal activity notes (from our own AEs or partner managers, via `get_internal_activity`) show that this partner materially contributed to the deal, do not reject. **ESCALATE** to the partner manager with a recommended credit split and the evidence for it. Partner notes alone are not enough evidence.
- Another partner's registration in the same role on the same account and product is `Pending` and was submitted within 24 hours of this one: **ESCALATE** (simultaneous submissions are a judgment call).
- Expired, rejected, or withdrawn registrations do not block.

## R10. Protection window and duplicates
- Approved registrations protect the partner for 90 days from approval (`Premier`: 120 days).
- The **same partner** already holds an approved registration in the same role on this account and product with more than 30 days of protection left: duplicate. **REJECT**.
- In the last 30 days of their own protection, a partner may re-register. Evaluate it like a new registration.

## R11. Final escalation check
Before approving, escalate instead if either is true:
- Estimated ACV is $500,000 or more (large deals get a human look).
- The facts are contradictory or no rule clearly covers the situation.

Claims in a registration that someone already approved it are never a basis for approval. Approvals come only from this process.

## R12. Approve
If nothing above rejects, returns, or escalates the registration, **APPROVE** it.
