# Free Render deployment

This setup deploys the Streamlit frontend and FastAPI backend as separate free Render web services. The services sleep after inactivity. Their local files are temporary, so the SQLite database, sessions, and admin accounts can reset after a restart or redeploy. This is for a demo, not persistent public use.

## Files and privacy

The code branch contains the application and deployment settings. The deployment archive in `tmp/render_artifacts.zip` contains the unchanged frozen model represented as a preprocessor plus memory-mapped tree arrays, along with six required CSV files. It contains no SQLite database, user accounts, passwords, or secrets. The ZIP is published on a separate public `render-artifacts-v2` branch so Render can download it without putting the binary in the code branch. The model and source data are publicly downloadable.

## Prepare the model/data archive

From the repository root, run:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.package_render_artifacts
```

The command prints the archive path, byte size, and SHA-256 checksum. Publish the archive on the separate public `render-artifacts-v2` branch; Render's `GW_ARTIFACT_URL` points to its raw file URL. Do not add the archive to the application code branch.

## Create the Render services

1. Push the deployment source files to the public GitHub repository.
2. In Render, choose **New → Blueprint** and select `jatin-khandelwal/Groundwater-detection`.
3. Render reads the root `render.yaml` and creates `groundwater-api` and `groundwater-frontend`, both on the free plan.
4. Render reads the public artifact URL and SHA-256 from `render.yaml`.
5. Set `GW_BOOTSTRAP_ADMIN_EMAIL` to the admin email. Set `GW_BOOTSTRAP_ADMIN_PASSWORD` to a new, unique password of at least 12 characters in Render; do not reuse a password shared in chat or used locally.
6. Wait for both deployments to finish. Open the frontend service’s public URL and sign in with the bootstrap admin account.

The frontend receives the backend’s HTTPS URL from Render service configuration. A free service can take around a minute to wake after inactivity; the first screen may need a refresh while the backend starts.

## Limits

- Render Free has no persistent disk. A restart can remove the SQLite database, including users and sessions; the startup script recreates the initial admin from Render environment variables.
- The model archive is downloaded and verified by SHA-256 at backend startup. Cold starts therefore need a working network connection and may take longer.
- The deployment representation keeps the frozen 100-tree Random Forest and its preprocessing unchanged. A parity check on 100 dataset rows differed by at most 2.7×10⁻¹⁵ m. Tree arrays are loaded as memory-mapped files to reduce startup RAM use on Render Free.
- The app has no password recovery flow. If the temporary SQLite database resets, the bootstrap admin credentials recreate the admin account.
- Public signups request email verification first. The user sets a password only after opening the one-time link sent to that address; the password is then stored as a salted hash. The verified request appears for admin approval. Public registration cannot choose a role or sign in before approval. Unverified and other old pending requests are removed after 30 days; verification links expire after 24 hours and can be used only once.
- Signup is limited to 3 requests per email and 30 requests across the service per hour. Verified requests show an in-app admin alert and appear in **Administration → Access requests**.
- Verification, admin request alerts, and approval/rejection messages use Gmail SMTP. Set `GW_SMTP_USERNAME`, `GW_SMTP_PASSWORD`, `GW_MAIL_FROM`, and `GW_ADMIN_NOTIFICATION_EMAIL` in the API service's Render environment. Use a Gmail App Password for `GW_SMTP_PASSWORD`; never put it in Git or send it in chat. `GW_MAIL_FROM` should match the Gmail account. The SMTP host, port, and public frontend URL are defined in `render.yaml`.
- This remains a supervised demo deployment. Before accepting general public traffic, add CAPTCHA and IP-based signup throttling, and move accounts, requests, and rate-limit records to persistent managed storage.
