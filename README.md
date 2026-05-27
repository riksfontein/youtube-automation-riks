# YouTube Automation System

Fully automated YouTube documentary production for Ancient Earth Cinema, The Global Intel Analyst, and The AI Bible Forensic.

---

## How It Works

**Four stages per video:**

| Stage | What happens | Trigger |
|-------|-------------|---------|
| 1 | Research 5 competitor videos, send Checkpoint 1 email | GitHub Actions schedule |
| 2 | Generate script from selected video, send script approval | You select video in GitHub |
| 3 | Generate 5 production documents, TTS, thumbnails | You approve script in GitHub |
| 4 | Assemble video + upload to YouTube | You upload assets and trigger in GitHub |

**Schedule:**
- Monday + Friday: Ancient Earth Cinema
- Tuesday + Saturday: The Global Intel Analyst  
- Wednesday + Sunday: The AI Bible Forensic
- Thursday: Off

---

## Setup Instructions

### Step 1 — Create the GitHub repository

1. Go to github.com and sign in as riksfontein
2. Click the **+** button → **New repository**
3. Repository name: `youtube-automation`
4. Set to **Private**
5. Click **Create repository**
6. Upload all files from this folder to the repository

### Step 2 — Add GitHub Secrets

Go to your repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add each of these secrets:

| Secret Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key from console.anthropic.com |
| `ELEVENLABS_API_KEY` | `sk_f231615b2420eb8037cddf824bacbd18d5868ff093c2a7de` |
| `SUBSCRIBR_API_KEY` | `150\|Q6U1nPgPPHqMcDIuoaKT6bb0jp1dabVjRRVgV0htd6a71d53` |
| `VIDIQ_API_KEY` | `vidiq_dXYThqOrAhnATen7ca4cJPChedJb3QXvVekbRjIU` |
| `RESEND_API_KEY` | `re_NZcQG8gR_FDeoC2oVfJQxoJnPQbnnkC5L` |
| `YOUTUBE_CLIENT_ID` | `723099509913-gq0as537ltjqfpnsmr30c7eddk3rq8ei.apps.googleusercontent.com` |
| `YOUTUBE_CLIENT_SECRET` | `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` |
| `YOUTUBE_REFRESH_TOKEN_MAIN` | Your OAuth refresh token from the auth script |
| `GOOGLE_DRIVE_FOLDER_ID` | The folder ID of your YouTube-Automation folder in Drive |
| `GITHUB_PAT` | A GitHub Personal Access Token (see Step 3) |

### Step 3 — Create a GitHub Personal Access Token

This allows the automation to trigger workflows from emails.

1. Go to github.com → **Settings** (your profile) → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. Click **Generate new token**
3. Name: `YouTube Automation`
4. Expiration: No expiration (or 1 year)
5. Scopes: check **workflow** and **repo**
6. Click **Generate token** — copy it
7. Add it as the `GITHUB_PAT` secret

### Step 4 — Create the Google Drive folder

1. Open Google Drive
2. Create a folder named `YouTube-Automation`
3. Inside it, create subfolders: `AE`, `GIA`, `BF`
4. Inside each channel folder, create: `reference-library`
5. Copy the folder ID from the URL: `drive.google.com/drive/folders/THIS_PART`
6. Add it as the `GOOGLE_DRIVE_FOLDER_ID` secret

### Step 5 — Upload reference images to Drive

Upload your NBP composites and map reference images to the correct folders:
- `YouTube-Automation/AE/reference-library/` — all AE composite and map images
- `YouTube-Automation/GIA/reference-library/` — all GIA composite and map images  
- `YouTube-Automation/BF/reference-library/` — all BF composite and map images

### Step 6 — Update state.json with reference image URLs

After uploading, copy the Google Drive sharing URLs for each reference image and add them to `state.json` in the `reference_library` section for each channel.

### Step 7 — Enable GitHub Actions

Go to your repository → **Actions** → click **Enable Actions**

---

## Running a Test

To test the system without waiting for the schedule:

1. Go to **Actions** → **Stage 1 — Research & Competitor Selection**
2. Click **Run workflow**
3. Select channel: `AE`
4. Click **Run workflow**

You should receive a Checkpoint 1 email at info@croki.store within 5 minutes.

---

## How to Respond to Emails

**Checkpoint 1 email (competitor selection):**
1. Review the 5 videos in the email
2. Click **SELECT THIS VIDEO →** on your chosen video
3. This opens GitHub Actions — click **Run workflow**
4. Fill in: channel, selected video URL, video title, job ID (shown in email)
5. Click Run

**Checkpoint 2 email (script approval):**
1. Read the script
2. Click **APPROVE — START PRODUCTION**
3. This opens GitHub Actions — click **Run workflow**
4. Fill in: channel, job ID, action: `approve`
5. Click Run

**Documents email:**
1. Download all 5 attached Word documents
2. Use Doc 2 in Google Flow (VEO Automation extension) to generate images
3. Use Doc 3A/3B/3C to generate videos
4. Upload to the Google Drive folder shown in the email
5. Click **ASSETS READY — START ASSEMBLY**
6. In GitHub: enter channel, job ID, and Drive folder URL

---

## File Structure

```
youtube-automation/
├── .github/workflows/
│   ├── stage1_research.yml     — Scheduled research
│   ├── stage2_script.yml       — Script generation  
│   ├── stage3_documents.yml    — Document generation
│   └── stage4_assembly.yml     — Assembly + upload
├── src/
│   ├── main.py                 — Master orchestration
│   ├── research.py             — Three-layer competitor research
│   ├── subscribr.py            — Subscribr API integration
│   ├── documents.py            — 5 Word document generators
│   ├── references.py           — Reference image analysis
│   ├── tts.py                  — ElevenLabs TTS + timestamps
│   ├── assembly.py             — FFmpeg video assembly
│   ├── youtube.py              — YouTube upload
│   ├── drive.py                — Google Drive integration
│   ├── email_sender.py         — Resend email sending
│   └── state.py                — State management
├── state.json                  — Channel rotation tracking
├── requirements.txt
└── README.md
```

---

## Adding New Channels

When Elite Chronicles (or any new channel) is ready:

1. Add a new entry to `state.json` with the channel config
2. Add the `schedule_days` field with the days to run
3. Update the schedule cron in `stage1_research.yml`
4. Add the YouTube OAuth token as a new secret
5. Add the Subscribr channel ID

---

## Troubleshooting

**Research returns no videos:**
- Check vidIQ and NexLev API connections in GitHub Actions logs
- Try running stage 1 manually with a different channel

**Script generation times out:**
- Subscribr can take up to 8 minutes per step
- If it fails, re-run stage 2 with the same job ID

**FFmpeg assembly fails:**
- Check that all video clips are numbered 001_video.mp4 format
- Ensure images folder has matching numbers to videos folder
- Check GitHub Actions logs for specific error

**YouTube upload fails:**
- Verify OAuth refresh token is valid
- Check that the Google Cloud project has YouTube Data API v3 enabled
