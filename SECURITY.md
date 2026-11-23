# Security policy

Ask Katy is a portfolio project with a public recruiter experience and a private
administration area. The source repository intentionally contains fictional demo
applications only. Production application content and credentials are not source code.

## Report a vulnerability

Please email [katyannhenning@gmail.com](mailto:katyannhenning@gmail.com) with
`Ask Katy security` in the subject. Include the affected route, the behavior you
observed, and reproduction steps that do not expose another person's data.

Do not put API keys, passwords, session cookies, private application URLs,
résumés, recruiter questions, or other private data in a public GitHub issue.
This personal portfolio project does not currently offer a paid bug bounty.

## Public/private boundary

The public repository may contain application code, tests, fictional fixtures,
deployment templates, and placeholder environment-variable names. It must not contain:

- `.env` files, private keys, access tokens, or production server identities
- SQLite databases, uploaded résumés, logs, or database backups
- real job descriptions, tailored application copy, or recruiter-question history

Those values live in ignored local files or outside the production web root. The
OpenAI key is read only by the backend. Recruiter browsers never receive it.

## Release checks

Run this before preparing a public source snapshot:

```bash
python scripts/public_release_audit.py
python scripts/public_release_audit.py --history
```

GitHub Actions repeats the audit, backend tests, frontend tests, and production
frontend build. If a real secret is ever exposed, revoke or rotate it first; deleting
the visible file is not sufficient because Git history and existing clones may retain it.
