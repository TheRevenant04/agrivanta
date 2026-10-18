# Agrivanta — MVP Scope Definition

**Product:** Agrivanta  
**Status:** MVP scope agreed; implementation and technology decisions deferred.

## 1. Product vision

Agrivanta is a responsive web application for professionally managed commercial crop farms. It brings farm operations and financial records together so owners and farm managers can track activities, manage resources, monitor budgets, record harvests and sales, and understand profitability at field and crop-cycle level.

Its AI analyst answers natural-language questions using recorded farm data, controlled data access, deterministic calculations, and traceable evidence.

## 2. Target users and boundaries

- **Primary users:** Farm owners and farm managers, with role-based access for workers.
- **Business scope:** One farm per business.
- **Agricultural scope:** Crop farming, supporting annual and perennial crops.
- **Platform:** Responsive web application for desktop, tablet, and mobile browsers.
- **Operating model:** Online-only.
- **Data entry:** Manual forms and CSV/Excel imports.
- **Accounting boundary:** Farm management accounting, not a replacement for formal accounting software.
- **Workflow model:** Standard core workflows with limited farm-level customization.

## 3. Core functional scope

### 3.1 Farm and crop-cycle management

- Configure one farm and its fields.
- Support user-defined crops, varieties, and measurement units.
- Support independent crop cycles per field, including overlapping cycles.
- Support annual and perennial crops.
- Support calendar reporting periods and farm-defined agricultural seasons.
- Provide guided onboarding to configure the farm, fields, crops, and initial records.
- Formally close crop cycles and lock them unless an authorized user reopens them.
- Preserve historical records for closed cycles.

### 3.2 Production planning and operations

- Plan activities, resource needs, input quantities, labour, equipment, budgets, and expected yields.
- Provide standard activity templates and allow custom activities.
- Example activities include land preparation, planting, fertilizing, spraying, and harvesting.
- Track activity statuses: planned, in progress, completed, and overdue.
- Detailed planned-versus-actual activity variance analysis is out of scope.
- Provide essential in-app notifications for overdue activities.

### 3.3 Inventory and resources

- Track stock purchases, usage, current quantities, and costs.
- Link input consumption and costs to crop-cycle profitability.
- Support worker profiles, activity assignments, assigned hours, and labour costs.
- Track equipment assignments, usage, and associated operating costs.
- Include basic supplier and customer profiles linked to relevant transactions.
- Provide low-stock notifications.
- Exclude equipment maintenance, payroll, leave, and full attendance management.

### 3.4 Costs, budgets, and payments

- Record purchases, expenses, direct costs, overheads, and basic receipts and payments.
- Link payments to sales and expenses where applicable.
- Support overall crop-cycle budgets and cost-category budgets.
- Provide budget-versus-actual reports.
- Support recurring expense templates and reminders; do not automatically create recurring transactions.
- Allow overheads to remain at farm level or be optionally allocated to fields or crop cycles using defined rules.
- Make shared-cost allocation rules transparent and reproducible.
- Distinguish crop operating surplus from results after allocated overheads.
- Support break-even calculations using recorded costs and explicit assumptions.
- Allow users to enter expected yields and selling prices manually, with historical farm data available as a reference.
- Use one reporting currency per farm.
- Do not provide full bookkeeping, general ledger, accounts payable/receivable, bank reconciliation, or advanced cash-flow management.

### 3.5 Harvests and sales

- Record harvest quantity, date, field, crop cycle, and unit.
- Record sales with customer, crop, quantity sold, selling price, and date.
- Keep harvested quantities, sold quantities, unsold produce, and actual revenue distinct.
- Record basic money received and paid.
- Exclude crop-loss tracking, quality grading, advanced post-harvest management, invoicing, and receivables management.

### 3.6 Reporting and profitability

- Provide a combined KPI dashboard with visual trends, comparisons, and detailed reports.
- Provide predefined operational and financial reports covering operations, inventory, costs, harvests, sales, budgets, and profitability.
- Support profitability reporting by field, crop cycle, season, and whole farm.
- Support historical and cross-field yield comparisons, using comparable units and clearly identified reporting periods.
- Provide break-even calculations based on recorded costs and explicit assumptions.
- Export generated reports as PDF, Excel, and CSV.
- Exclude custom report builders and raw-data exports from the MVP.

### 3.7 AI analyst

- Provide a natural-language chat interface for questions across all supported farm data.
- Use approved database queries and calculation tools, subject to the user's access permissions.
- Keep the AI read-only: it must not modify farm records or prescribe actions.
- Show traceable evidence in answers, including figures used, relevant fields and crop cycles, reporting periods, and calculation basis.
- Use deterministic calculations for financial and operational metrics; the LLM explains results rather than inventing figures.
- When data is insufficient or invalid, explain the limitation and identify the missing or incorrect data. Do not guess or silently treat missing values as zero.
- Clearly distinguish actuals, estimates, and assumptions.
- Evaluate AI answer factual accuracy, relevance, and calculation correctness using automated evaluations, human review, and regression tests after AI workflow changes.
- Start with a hosted LLM behind a provider-independent interface.
- Use realistic sample data with multiple fields, overlapping crop cycles, operational records, expenses, harvests, and sales.

## 4. Data entry, imports, and records

- Provide dedicated forms for purchases, expenses, stock usage, harvests, sales, and payments.
- Support manual entry and CSV/Excel imports.
- Historical records can be entered manually or imported.
- Imports must use a preview-and-confirm process:
  1. Validate the uploaded file.
  2. Show invalid records and duplicates.
  3. Allow corrections before import.
  4. Import only after user confirmation.
- Allow receipts and supplier invoices to be uploaded and linked to transactions.
- Automatic document extraction is excluded.
- Draft records may be deleted.
- Posted transactions must not be edited or deleted; corrections require reversal and replacement.
- Maintain a full change history and restrict sensitive actions to authorized users.
- Closed crop cycles remain locked unless an authorized user reopens them.

## 5. Financial integrity and data quality

These are mandatory product requirements:

- Calculate financial metrics deterministically.
- Block calculations when required data is missing or invalid and explain what needs correction.
- Do not fabricate figures or silently substitute assumptions.
- Make direct costs, shared costs, allocation rules, and overhead treatment transparent.
- Distinguish crop operating surplus from results after allocated overheads.
- Base break-even calculations on recorded costs and explicit assumptions.
- Preserve posted transactions and their audit history.
- Use reversal-and-replacement corrections for posted transactions.
- Validate imported records before including them in reports or AI analysis.
- Preserve closed-cycle history and prevent ordinary editing of closed cycles.
- Include scheduled database backups and a documented restore process.
- Include structured logs, error tracking, health checks, and performance metrics.

## 6. Users, notifications, and supporting features

- Role-based access for owners, farm managers, and workers.
- Guided farm setup.
- Essential in-app notifications for overdue activities, low inventory, budget overruns, and data-quality issues.
- Basic supplier and customer profiles linked to purchases, sales, and relevant transactions.
- Recurring expense templates with reminders.
- User-defined measurement units and conversion rules.
- One reporting currency per farm.
- Calendar reporting periods and farm-defined agricultural seasons.
- Basic transaction attachments for receipts and supplier invoices.
- PDF, Excel, and CSV exports for generated reports.

## 7. Explicitly excluded from the MVP

- Multiple farms per business or multiple-business management.
- Manager scoring and performance evaluation.
- Crop production loss tracking and loss analysis.
- Equipment maintenance and service scheduling.
- Payroll, leave, and full workforce attendance management.
- Produce quality grading and advanced post-harvest management.
- Full accounting, general ledger, accounts payable/receivable, invoicing, and bank reconciliation.
- Advanced cash-flow dashboards and payment scheduling.
- Multi-currency transaction conversion.
- Custom report builders and raw-data exports.
- Automatic generation of recurring expense transactions.
- Predictive yield or market-price forecasting.
- Automated extraction from receipts or invoices.
- External integrations beyond CSV/Excel import and export.
- Offline mode and native mobile apps.
- Proactive AI recommendations or actions.
- Detailed planned-versus-actual activity variance analysis.

## 8. MVP success criterion

The MVP is successful when a farm manager can complete this workflow end to end:

1. Configure a farm, fields, crops, and crop cycles.
2. Create a production plan and schedule farm activities.
3. Record inventory purchases and usage, labour, equipment, and expenses.
4. Track budgets and resource availability during the crop cycle.
5. Record harvests, sales, and money received or paid.
6. Close a crop cycle and preserve its history.
7. Generate reliable operational and profitability reports.
8. Ask the AI questions and receive evidence-backed answers.
9. Evaluate AI answer accuracy and calculation correctness against known results.

## 9. Scope summary

Agrivanta is an integrated farm operations and profitability product with a measurable AI analyst—not merely a financial dashboard or an AI chatbot. The MVP prioritizes a reliable end-to-end workflow before expanding into advanced farm automation, forecasting, or integrations.

Technology selection, detailed architecture, database design, implementation tasks, and deployment decisions are deferred to a later phase.
