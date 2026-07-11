# Contributing to MAD

Team workflow for the MAD greenhouse digital-twin project.

## Branch workflow

- `main` is protected — never commit to it directly.
- Create a branch per task: `feature/<short-name>`, `fix/<short-name>`, or `docs/<short-name>`.

```bash
git checkout main && git pull
git checkout -b feature/dashboard-alerts
# ...work, commit...
git push -u origin feature/dashboard-alerts
```

Then open a Pull Request on GitHub and request a review from a teammate. Merge only after at least one approval.

## Commit messages

Short imperative subject line, optional body explaining why:

```
Add CO2 alert banner to dashboard

Threshold matches the fan rule (900 ppm) so operators see
why the fan switched on.
```

## Before you push

1. Bring the stack up and confirm it's healthy: `bash launch.sh` then `docker compose ps` (all services Up).
2. Open the dashboard (http://localhost:8050) and wiring page (http://localhost:8888) — data flowing.
3. If you touched the model pipeline: `python3 generate_dataset.py --train` runs without errors.
4. Never commit generated artifacts: `mad_project/data/*.csv`, `mad_project/model/*.pkl`, or your local `.env` (the `.gitignore` covers these — don't force-add them).

## Local setup after cloning

```bash
cp mad_project/.env.example mad_project/.env   # local config (defaults work as-is)
python3 setup.py                               # environment checks
python3 generate_dataset.py --train            # build dataset + model
bash launch.sh                                 # bring up the stack
```

## Project conventions

- The 6-feature vector order `[temp_dht, temp_ds18, humidity, soil_moisture, co2, light_intensity]` is fixed across the whole stack — never reorder it.
- MQTT topics: `greenhouse/sensor`, `greenhouse/command`, `greenhouse/bridge` (retained). New topics need team agreement first.
- Each service owns its own folder under `mad_project/` with its `Dockerfile` and `requirements.txt` — keep dependencies per-service.
