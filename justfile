# Local commands. Run them inside the devenv shell (`direnv allow` or
# `devenv shell`). They call the same scripts the AMP runs in CML.

# Run the runbook and application tests.
test:
    uv run --extra dev pytest

# Write the status snapshot. Same script as the CML prepare job.
prepare:
    uv run python 1_job-prepare-project/job.py

# Serve the application on port 8123. CML sets CDSW_APP_PORT instead.
app:
    uv run python 2_app-serve/app.py
