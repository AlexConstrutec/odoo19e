# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Company-level fiscal/legal fields for Guatemala: `res.company.regimen_iva` (VAT regime before the SAT), `nombre_legal` (legal name), `codigo_establecimiento` (SAT establishment code). Added via `views/res_company_views.xml` (inherits `base.view_company_form`), right before `company_registry`.

## Why this exists instead of installing `l10n_gt_edi`

Stock Odoo already ships a Guatemala electronic-invoicing module (`l10n_gt_edi`) with an equivalent field (`res.company.l10n_gt_edi_vat_affiliation`, same 8 selection values) — but that module is **hardcoded to INFILE, S.A.** as the certifier (see `l10n_gt_edi/models/res_company.py`: field labels literally say "Infile Web Service Provider", "Infile Key (LlaveAPI)", and the invoice report prints "Certificador: INFILE, S.A." as static text). Since the client's actual FEL certifier wasn't confirmed at the time this was built, this module replicates just the 3 non-certifier-specific fields (regime + legal name + establishment code) so reports/payroll can reference them now, without committing to Infile.

## Known gap (by design, not by accident)

**No electronic-invoicing (FEL) integration yet.** `l10n_gt_edi`'s certifier-specific fields (`l10n_gt_edi_service_provider`, `l10n_gt_edi_infile_key`, `l10n_gt_edi_infile_token`, `l10n_gt_edi_ws_prefix`, `l10n_gt_edi_phrase_ids`) were deliberately **not** replicated — "las funciones de certificación las haremos después" (per the user). When that scope is picked up, first confirm which certifier Construtec actually uses before building against it (don't assume Infile).

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_account_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
