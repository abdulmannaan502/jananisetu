# Publishing the evaluator demo on Render (you do these steps; ~15 minutes)

**Status: prepared, not deployed, not verified in the cloud.** I verified the start command locally on an empty database (import app, seed, uvicorn, doctor login returns a token). I could not run Docker here, so the image build and Render itself are untested.

## What is exposed
Anyone with the URL can open the app and see the demo accounts and the shared demo password on the login screen. Data is synthetic (names, phones, grants). WhatsApp is the local simulator. Delete the service after judging (step 6).

## Steps
1. Create a **private** GitHub repository from this project and push it. Do not commit `.env`, `.venv`, `node_modules` or `jananisetu_release_backup_*.zip` (check `.gitignore`). Private is fine: Render reads it with your authorisation, evaluators never see the code.
2. On render.com sign in with GitHub, choose **New + > Blueprint**, select the repository. Render reads `render.yaml` (added at the project root) and builds the Dockerfile (Tesseract is installed in the image).
3. Wait for the build (about 5-10 minutes) until the service shows **Live**. The URL looks like `https://jananisetu-demo.onrender.com`.
4. Check in a private/incognito window: `<URL>/api/health` must show `"status":"ok"`, `"messaging":"simulated"`, `"ocr_engine":"tesseract-5"`; then open `<URL>`, sign in as the doctor, and follow the test path in `FORM_FIELDS_TO_PASTE.md`.
5. Free plan caveats: the service sleeps after about 15 minutes idle and takes roughly a minute to wake; data resets on every restart (it re-seeds). Open the URL a few minutes before submitting, and mention "may take about a minute to wake" in the form's access instructions. A paid instance avoids sleeping.
6. After the results are out, delete the service in the Render dashboard.

## If the build fails
Send me the Render build log. Likely causes: the frontend build step in the Dockerfile (`app/static/dist` path) or the `dockerCommand` quoting.

## Then
Send me the working URL. I will put it on slide 12 and in the brief, and fill the MVP field text. I will not add a URL I haven't opened myself.
