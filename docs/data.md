# Data and generation

No real employee, payroll, or bank record appears anywhere in this project. Every
row is generated locally from a seed, so the same seed gives the same dataset.

## The fictional organisation

Monthly payroll, GBP, 250 employees across eight departments and five UK
locations. Salaries are sampled inside rounded role-grade bands and nudged by a
regional factor. Overtime and bonuses appear probabilistically rather than on a
schedule.

Salary bands and regional factors are loose approximations, informed by:

- ONS Annual Survey of Hours and Earnings, occupation tables —
  <https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/datasets/occupation2digitsocashetable2>
- ONS ASHE, region by occupation —
  <https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/datasets/regionbyoccupation2digitsocashetable3>
- HMRC rates and thresholds for employers —
  <https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2025-to-2026>

These give aggregate shape only. Nothing here reproduces survey microdata.

PAYE, National Insurance, and pension figures are deliberately simplified. The
project is about anomaly detection, not payroll compliance, and the deduction
maths should not be treated as correct for any real purpose.

Bank accounts exist only as opaque tokens. There is no account number to store or
leak, and a token change is detectable without the underlying detail ever being
present.

## Tables

| Table | What it holds |
| --- | --- |
| `employees` | Code, department, job title, grade, location, salary, start and end dates |
| `bank_accounts` | Token history per employee with effective dates |
| `payroll_runs` | Period, payment date, status |
| `payments` | Pay components, deductions, net pay, destination token |
| `anomaly_labels` | Ground truth: which payment, which type, how it was injected |
| `model_runs` | Version, feature list, parameters, metrics |
| `anomaly_alerts` | Score, severity, evidence |
| `investigations` | Outcome, note, investigator, timestamp |

`anomaly_labels` is the important one to be careful about. It is written by the
generator and read only by the evaluation code. Nothing in the feature builder,
the controls, or the model touches it.

## Injected anomalies

Four of each, twenty-four in total on the default seed.

| Type | How it is injected |
| --- | --- |
| Duplicate payment | Every monetary and destination field copied into a second payment |
| Unexpected pay increase | Base pay multiplied by roughly 1.75 to 2.10 |
| Abnormal deduction | Other deductions set to 46% of gross |
| Recent bank change | Destination token changed two days before payment |
| Post-termination payment | A payment created in a period after the termination date |
| Invalid net/gross ratio | Net pay set to 108% of gross |

The injections are blunt on purpose. They are there to prove the controls fire and
to give the model something measurable to be scored against, not to imitate how
real payroll fraud looks.
