# YouTube Automation System

Fully automated YouTube documentary production for Ancient Earth Cinema, The Global Intel Analyst, and The AI Bible Forensic — with support for adding new channels at any time.

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

## Initial Setup

### Step 1 — Add GitHub Secrets

Go to repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add all 20 secrets. Names must match exactly.

| Secret Name | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `ELEVENLABS_API_KEY` | elevenlabs.io → Profile → API Keys |
| `ELEVENLABS_VOICE_ID_AE` | Your custom AE voice ID from ElevenLabs |
| `ELEVENLABS_VOICE_ID_GIA` | Your custom GIA voice ID from ElevenLabs |
| `ELEVENLABS_VOICE_ID_BF` | Your custom BF voice ID from ElevenLabs |
| `SUBSCRIBR_API_KEY` | Subscribr dashboard → Settings → API |
| `SUBSCRIBR_CHANNEL_ID_AE` | Your AE channel ID in Subscribr (56655) |
| `SUBSCRIBR_CHANNEL_ID_GIA` | Your GIA channel ID in Subscribr (54904) |
| `SUBSCRIBR_CHANNEL_ID_BF` | Your BF channel ID in Subscribr (55636) |
| `VIDIQ_API_KEY` | Your vidIQ API key |
| `RESEND_API_KEY` | resend.com → API Keys |
| `RESEND_FROM_EMAIL` | The email address automation sends FROM |
| `RESEND_TO_EMAIL` | The email address you receive notifications at |
| `YOUTUBE_CLIENT_ID` | Google Cloud Console → APIs & Services → Credentials |
| `YOUTUBE_CLIENT_SECRET` | Google Cloud Console → APIs & Services → Credentials |
| `YOUTUBE_REFRESH_TOKEN_AE` | Run youtube_drive_auth.py → select Ancient Earth Cinema |
| `YOUTUBE_REFRESH_TOKEN_GIA` | Run youtube_drive_auth.py → select The Global Intel Analyst |
| `YOUTUBE_REFRESH_TOKEN_BF` | Run youtube_drive_auth.py → select The AI Bible Forensic |
| `GOOGLE_DRIVE_FOLDER_ID` | Folder ID of your YouTube-Automation folder in Drive |
| `GITHUB_PAT` | github.com → Settings → Developer settings → Personal access tokens (classic) → workflow + repo scopes |

### Step 2 — Create GitHub Personal Access Token

1. github.com → click profile picture → **Settings**
2. Scroll to bottom → **Developer settings**
3. **Personal access tokens** → **Tokens (classic)**
4. **Generate new token (classic)**
5. Name: `YouTube Automation` — Expiration: No expiration
6. Scopes: check **workflow** and **repo**
7. Click **Generate token** → copy it → add as `GITHUB_PAT` secret

### Step 3 — Create Google Drive folder structure

1. Create a folder named `YouTube-Automation` in Google Drive
2. Inside it create subfolders: `AE`, `GIA`, `BF`
3. Inside each channel folder create: `reference-library`
4. Copy the folder ID from the URL: `drive.google.com/drive/folders/THIS_IS_THE_ID`
5. Add as `GOOGLE_DRIVE_FOLDER_ID` secret

### Step 4 — Upload reference images

Upload your Nano Banana Pro composites and GPT Image 2 map and creature images to:
- `YouTube-Automation/AE/reference-library/`
- `YouTube-Automation/GIA/reference-library/`
- `YouTube-Automation/BF/reference-library/`

Then update `state.json` with the Google Drive file URLs for each image in the `reference_library` sections.

### Step 5 — Enable GitHub Actions

Repository → **Actions** → click **Enable Actions** if prompted.

---

## Running a Test

1. Go to **Actions** → **Stage 1 — Research & Competitor Selection**
2. Click **Run workflow**
3. Select channel: `AE`
4. Click **Run workflow**

You should receive a Checkpoint 1 email within 5 minutes.

---

## How to Respond to Emails

**Checkpoint 1 — Competitor video selection:**
1. Review the 5 videos
2. Click **SELECT THIS VIDEO →** — opens GitHub Actions
3. Click **Run workflow** — fill in channel, job_id, video URL, video title
4. Click Run

**Checkpoint 2 — Script approval:**
1. Read the script
2. Click **APPROVE** or **REGENERATE** — opens GitHub Actions
3. Fill in channel, job_id, action (approve or regenerate)
4. Click Run

**Documents email:**
1. Download all 5 attached Word documents
2. Doc 2: generate images in Google Flow using VEO Automation extension
3. Doc 3A: generate videos using Auto Meta extension (Meta AI)
4. Doc 3B: generate videos using VEO Automation extension (VEO3.1)
5. Doc 3C: generate videos using Grok extension (Grok Aurora — 6s or 10s per scene)
6. Upload images to `images/` subfolder in the Drive folder shown in the email
7. Upload videos to `videos/` subfolder
8. Files must be named: `001_image.jpg`, `002_image.jpg` etc. and `001_video.mp4`, `002_video.mp4` etc.
9. Click **ASSETS READY** — opens GitHub Actions
10. Fill in channel, job_id, Drive folder URL
11. Click Run

---

## Schedule

| Day | Channel | UTC time |
|-----|---------|----------|
| Monday | Ancient Earth Cinema | 06:00 |
| Tuesday | The Global Intel Analyst | 06:00 |
| Wednesday | The AI Bible Forensic | 06:00 |
| Thursday | Off | — |
| Friday | Ancient Earth Cinema | 06:00 |
| Saturday | The Global Intel Analyst | 06:00 |
| Sunday | The AI Bible Forensic | 06:00 |

---

## Adding a New Channel (Elite Chronicles, Digital Dread, etc.)

Follow all 9 steps below in order. Do not skip any.

### Step 1 — Subscribr setup (do this first)

Complete all 5 setup steps inside Subscribr for the new channel before anything else:
1. Channel Profile
2. Script Defaults
3. Ideation settings
4. Reference Library (upload background and character images)
5. Template (paste the channel's script template)

Note the Subscribr channel ID from the URL when inside the channel.

### Step 2 — Add GitHub Secrets

Add these secrets for the new channel. Replace `XX` with the channel code (EC for Elite Chronicles, DD for Digital Dread, etc.):

| Secret Name | Value |
|---|---|
| `ELEVENLABS_VOICE_ID_XX` | The ElevenLabs voice ID for this channel |
| `SUBSCRIBR_CHANNEL_ID_XX` | The Subscribr channel ID for this channel |
| `YOUTUBE_REFRESH_TOKEN_XX` | Run youtube_drive_auth.py → select the brand account |

### Step 3 — Get the YouTube channel ID

1. Go to the channel on YouTube
2. Click the channel name to go to the channel page
3. The URL will show: `youtube.com/channel/UCxxxxxxxxxxxxxxxxx`
4. Copy the `UCxxxxxxxxxxxxxxxxx` part — this is the channel ID

### Step 4 — Update state.json

Add a new channel block. Copy the structure from an existing channel (AE, GIA, or BF) and update:
- `channel_name` — full channel name
- `subscribr_channel_id` — from Step 1
- `youtube_channel_name` — YouTube channel name
- `voice_id` — ElevenLabs voice ID
- `caption_font` — Bebas Neue (all channels except BF which uses Cinzel)
- `caption_uppercase` — true for all channels except BF
- `rotations` — the 5 rotation names for this channel
- `keywords_by_rotation` — 5 keywords per rotation for competitor research
- `youtube_channel_id` — from Step 3
- `google_drive_base_path` — e.g. `YouTube-Automation/EC`
- `schedule_days` — which days of the week (0=Monday, 1=Tuesday etc.)

### Step 5 — Update youtube.py

Add the new channel to two dictionaries in `src/youtube.py`:

```python
CHANNEL_CATEGORY_IDS = {
    "AE":  "28",
    "GIA": "25",
    "BF":  "27",
    "EC":  "25",   # add this line — use correct YouTube category ID
}

CHANNEL_YOUTUBE_IDS = {
    "AE":  "UCzazMPj4dWuXuLj74aVu9WQ",
    "GIA": "UCrNSYDPBcQRNzpJlA3hEXnA",
    "BF":  "UCvFKEzLIek3v05fqvAQbudA",
    "EC":  "UCxxxxxxxxxxxxxxxxx",   # add this line with actual channel ID
}

CHANNEL_TOKEN_SECRETS = {
    "AE":  "YOUTUBE_REFRESH_TOKEN_AE",
    "GIA": "YOUTUBE_REFRESH_TOKEN_GIA",
    "BF":  "YOUTUBE_REFRESH_TOKEN_BF",
    "EC":  "YOUTUBE_REFRESH_TOKEN_EC",   # add this line
}
```

### Step 6 — Update the GitHub Actions workflow files

In `.github/workflows/stage1_research.yml` — add the new channel to the `workflow_dispatch` options:
```yaml
options:
  - AE
  - GIA
  - BF
  - EC    # add this line
```

In `.github/workflows/stage1_research.yml` — add a new cron line for the schedule:
```yaml
- cron: '0 6 * * 4'   # example: Thursday for EC
```

In `.github/workflows/stage3_documents.yml` — add new secrets to the env section:
```yaml
ELEVENLABS_VOICE_ID_EC: ${{ secrets.ELEVENLABS_VOICE_ID_EC }}
SUBSCRIBR_CHANNEL_ID_EC: ${{ secrets.SUBSCRIBR_CHANNEL_ID_EC }}
```

In `.github/workflows/stage4_assembly.yml` — add the new token to the env section:
```yaml
YOUTUBE_REFRESH_TOKEN_EC: ${{ secrets.YOUTUBE_REFRESH_TOKEN_EC }}
```

In `.github/workflows/stage2_script.yml` — add new channel to the options list.

### Step 7 — Generate reference images

Generate all reference images for the new channel:
- NBP composite images (character × environment combinations)
- GPT Image 2 map reference images (one per rotation that needs maps)
- GPT Image 2 species or character reference images

Upload all to `YouTube-Automation/XX/reference-library/` in Google Drive.

### Step 8 — Update state.json reference_library URLs

After uploading reference images, copy the Google Drive sharing URL for each image and add it to the `reference_library` section of the new channel in `state.json`.

### Step 9 — Update references.py

Add the new channel's reference keyword mappings to `REFERENCE_KEYWORDS` in `src/references.py` so the system can automatically identify which reference image to use for each scene.

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

## Troubleshooting

**Research returns no videos:**
Check vidIQ and NexLev API connections. Try running Stage 1 manually.

**Script generation times out:**
Subscribr can take up to 8 minutes per step. Re-run Stage 2 with the same job ID and action = regenerate.

**Assembly fails:**
Confirm clips are named `001_video.mp4` format and all scene numbers are present. Check GitHub Actions logs for the specific error.

**YouTube upload posts to wrong channel:**
Check the GitHub Actions log for the line `Token gives access to: [channel name]`. If it shows the wrong channel, regenerate the OAuth token for that channel by running `youtube_drive_auth.py` again and selecting the correct brand account.

**YouTube upload fails with 401:**
The refresh token has expired or been revoked. Run `youtube_drive_auth.py` again for that channel and update the secret.

**Email not received:**
Check the Resend dashboard for delivery status. Verify `RESEND_FROM_EMAIL` is a verified domain in your Resend account.
