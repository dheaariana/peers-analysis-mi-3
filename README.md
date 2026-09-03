# PEARL MI3 — Coal Mining Contractor Peer Finder

Focused pilot for coal-related mining services. The application combines the structure of the previous departmental portfolio database with qualitative peer-screening criteria requested by senior CRM.

## Main improvements

- Imports the existing `Input Data` workbook structure for portfolio mapping.
- Filters coal-related contractors as the pilot population.
- Accepts any new target company through manual business-pattern profiling.
- Lets users select a Mining & Energy contractor directly from an imported workbook.
- Starts unknown-company profiles blank, so another company's assumptions are never reused.
- Requires the user to press `Cari peers` before results are recalculated.
- Selects peers based on operating model and growth pattern—not loan size or financial ratios.
- Explains why margin/performance may differ across otherwise similar contractors.
- Lets the PIC update the peer database without editing Python code.
- Can add a new target to the current session and export it into the updated CSV.
- Exports a peer shortlist and comparison workbook for CRM follow-up.
- Searches recent public publications using the company name.
- Scrapes user-approved public/official HTML pages and records the source as `Pending CRM Validation`.
- Never overwrites structured peer fields automatically; CRM reviews the evidence first.

## Streamlit deployment

Upload these four files side-by-side to the GitHub repository root:

1. `app.py`
2. `peer_database.csv`
3. `requirements.txt`
4. `README.md`

In Streamlit Community Cloud, select:

- Repository: your repository
- Branch: `main`
- Main file path: `app.py`

After committing the files, the existing Streamlit application normally redeploys automatically. If not, open **Manage app**, select the three-dot menu, and choose **Reboot app**.

## Database governance

The bundled peer profiles are illustrative and marked `Pending CRM Validation`. Replace each source and period with verified public/approved information. Do not upload confidential Bank Mandiri or debtor information to a public Streamlit deployment. For internal data, use an internally approved hosting environment or a sanitized extract.

## Peer methodology

Eligibility requires a comparable mining-contractor role and subsector. Weighted matching then considers service scope, commodity, contract profile, tariff model, customer profile/concentration, geography, fleet model, fuel-cost allocation, growth stage, growth pattern, and revenue-growth band. The result measures operational comparability only; CRM still obtains and analyzes the latest financial statements separately.

## Public-source update workflow

Open `Pembaruan publik`, enter the company name, search recent publications, and paste up to five official/public page URLs. PEARL extracts visible text, highlights topics requiring review, and allows the CRM to record one source with `Pending CRM Validation` status. Complete or correct the structured profile in `Maintain database`, download the latest CSV, and replace `peer_database.csv` in GitHub to persist the update.
