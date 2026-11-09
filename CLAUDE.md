# Project-Adrian

The repo for all of Josh's Claude Duet work: pipelines, scheduled GitHub Actions and the scripts behind them.

## Python style

All Python here follows `docs/python_style.md`.

- Applies everywhere: Shape of a function, Comments (the Project-Adrian scripts row: one short sentence, about 8 words), Use / not, Names, Trust, and Grading.
- Versuz only: the Django parts (views, models, `request.data`, `to_dict`, serializers, AuthView). Ignore them for scripts here.
- A new style call from Josh goes in `docs/python_style.md` in the same task.

## Working rules

- Secrets live only in GitHub encrypted secrets, read at run time from the environment. Never write a key, password or token into a file, a log or a commit.
- One exception: the GitHub dispatch token lives in Supabase Vault as `github_dispatch_token`, so Supabase cron can start workflows.
- Plan first. Josh signs off on a plan before code is committed, a workflow is turned on or a table is created.
- Say "I don't know" rather than guess, and cite official docs for any limit or behaviour you rely on.
