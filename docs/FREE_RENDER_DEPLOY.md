# Free Render deployment

This setup deploys the Streamlit frontend and FastAPI backend as separate free Render web services. The services sleep after inactivity. Their local files are temporary, so the SQLite database, sessions, and admin accounts can reset after a restart or redeploy. This is for a demo, not persistent public use.

## Files and privacy

The Git repository contains application code and deployment settings. The deployment archive in `tmp/render_artifacts.zip` contains the unchanged frozen model represented as a preprocessor plus memory-mapped tree arrays, along with six required CSV files. It contains no SQLite database, user accounts, passwords, or secrets. Publishing it as a public GitHub Release makes the model and source data downloadable by anyone.

## Prepare the model/data archive

From the repository root, run:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.package_render_artifacts
```

The command prints the archive path, byte size, and SHA-256 checksum. Create a GitHub Release in `jatin-khandelwal/Groundwater-detection`, upload `tmp/render_artifacts.zip`, and copy its HTTPS download URL. Do not add this archive to a Git commit.

## Create the Render services

1. Push the deployment source files to the public GitHub repository.
2. In Render, choose **New → Blueprint** and select `jatin-khandelwal/Groundwater-detection`.
3. Render reads the root `render.yaml` and creates `groundwater-api` and `groundwater-frontend`, both on the free plan.
4. When prompted for the API variables, enter the GitHub Release asset URL and the printed SHA-256.
5. Set `GW_BOOTSTRAP_ADMIN_EMAIL` to the admin email. Set `GW_BOOTSTRAP_ADMIN_PASSWORD` to a new, unique password of at least 12 characters in Render; do not reuse a password shared in chat or used locally.
6. Wait for both deployments to finish. Open the frontend service’s public URL and sign in with the bootstrap admin account.

The frontend receives the backend’s HTTPS URL from Render service configuration. A free service can take around a minute to wake after inactivity; the first screen may need a refresh while the backend starts.

## Limits

- Render Free has no persistent disk. A restart can remove the SQLite database, including users and sessions; the startup script recreates the initial admin from Render environment variables.
- The model archive is downloaded and verified by SHA-256 at backend startup. Cold starts therefore need a working network connection and may take longer.
- The deployment representation keeps the frozen 100-tree Random Forest and its preprocessing unchanged. A parity check on 100 dataset rows differed by at most 2.7×10⁻¹⁵ m. Tree arrays are loaded as memory-mapped files to reduce startup RAM use on Render Free.
- The app has no password recovery flow. If the temporary SQLite database resets, the bootstrap admin credentials recreate the admin account.
