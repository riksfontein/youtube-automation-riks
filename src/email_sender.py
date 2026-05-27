"""
email_sender.py — Send all automation emails via Resend API.
Five email types:
  1. Checkpoint 1 — competitor video selection
  2. Checkpoint 2 — script approval
  3. Reference images — missing references notification
  4. Documents — production documents delivery
  5. Delivery — final video + metadata + YouTube Studio link
  6. Rotation change — notification when rotation switches
"""

import os
import json
import requests
from datetime import datetime
from typing import Optional

RESEND_API_KEY   = os.environ["RESEND_API_KEY"]
FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL") or "automation@croki.store"
TO_EMAIL   = os.environ.get("RESEND_TO_EMAIL") or "info@croki.store" 
RESEND_SEND_URL  = "https://api.resend.com/emails"

GITHUB_REPO    = os.environ.get("GITHUB_REPO", "riksfontein/youtube-automation")
GITHUB_ACTIONS = f"https://github.com/{GITHUB_REPO}/actions"


def _send(subject: str, html: str,
          attachments: Optional[list[dict]] = None) -> dict:
    """Send an email via Resend API. Never raises — logs error and continues."""
    from_email = os.environ.get("RESEND_FROM_EMAIL") or "automation@croki.store"
    to_email   = os.environ.get("RESEND_TO_EMAIL")   or "info@croki.store"
    api_key    = os.environ.get("RESEND_API_KEY", "")

    payload = {
        "from":    from_email,
        "to":      [to_email],
        "subject": subject,
        "html":    html
    }
    if attachments:
        payload["attachments"] = attachments

    if not api_key:
        print(f"[Email] SKIPPED (no RESEND_API_KEY): {subject[:60]}")
        return {"skipped": "no api key"}

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json"
        }
        resp = requests.post(RESEND_SEND_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 422:
            print(f"[Email] 422 error — check FROM domain is verified in Resend")
            print(f"[Email] From: {from_email} | To: {to_email}")
            print(f"[Email] Response: {resp.text[:300]}")
            return {"error": "422", "details": resp.text}
        resp.raise_for_status()
        result = resp.json()
        print(f"[Email] Sent: {subject[:60]} → {result.get('id', 'ok')}")
        return result
    except Exception as e:
        print(f"[Email] Failed to send '{subject[:40]}': {e}")
        return {"error": str(e)}


def _video_card(video: dict, index: int, job_id: str, channel: str) -> str:
    """Generate HTML card for a competitor video."""
    title      = video.get("title", "Unknown")
    channel_nm = video.get("channel_name", "Unknown")
    subs       = int(video.get("subscriber_count") or 0)
    views      = int(video.get("view_count") or 0)
    outlier    = video.get("outlier_score", 0)
    vph        = video.get("views_per_hour", 0)
    pub_date   = video.get("published_date", "")
    url        = video.get("video_url", "#")
    angle      = video.get("subscribr_angle", "")
    fmt        = video.get("subscribr_format", "Documentary")
    goals      = video.get("subscribr_goals", "")

    # GitHub Actions dispatch URL for stage 2
    dispatch_url = (
        f"https://github.com/{GITHUB_REPO}/actions/workflows/stage2_script.yml"
    )

    return f"""
<div style="border:1px solid #ddd;border-radius:8px;padding:20px;margin:16px 0;background:#f9f9f9">
  <div style="font-size:12px;color:#888;margin-bottom:4px">VIDEO {index}</div>
  <div style="font-size:17px;font-weight:bold;color:#1a1a1a;margin-bottom:8px">{title}</div>
  <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:12px">
    <div><span style="color:#888;font-size:11px">CHANNEL</span><br><strong>{channel_nm}</strong></div>
    <div><span style="color:#888;font-size:11px">SUBS</span><br><strong>{subs:,}</strong></div>
    <div><span style="color:#888;font-size:11px">VIEWS</span><br><strong>{views:,}</strong></div>
    <div><span style="color:#888;font-size:11px">OUTLIER</span><br><strong style="color:#d97706">{outlier:.1f}x</strong></div>
    <div><span style="color:#888;font-size:11px">VPH</span><br><strong>{vph:.0f}</strong></div>
    <div><span style="color:#888;font-size:11px">PUBLISHED</span><br><strong>{pub_date}</strong></div>
  </div>
  <div style="background:#fff;border-left:3px solid #3b82f6;padding:10px 14px;margin-bottom:12px;font-size:13px">
    <strong>Format:</strong> {fmt}<br>
    <strong>Angle:</strong> {angle}<br>
    <strong>Viewer goals:</strong> {goals}
  </div>
  <a href="{url}" target="_blank" style="color:#3b82f6;font-size:13px;margin-right:16px">▶ Watch video</a>
  <a href="{dispatch_url}" target="_blank"
     style="background:#16a34a;color:#fff;padding:8px 16px;border-radius:6px;font-size:13px;text-decoration:none;font-weight:bold">
    SELECT THIS VIDEO →
  </a>
  <div style="font-size:11px;color:#888;margin-top:8px">
    After clicking: In GitHub, click "Run workflow", enter job_id: <strong>{job_id}</strong>, 
    video URL: <code>{url}</code>, video title: <em>{title}</em>
  </div>
</div>"""


def send_checkpoint1(
    channel: str,
    rotation_name: str,
    videos_in_rotation: int,
    rotation_threshold: int,
    top_videos: list[dict],
    job_id: str
) -> dict:
    """Send Checkpoint 1 email with top 5 competitor videos."""
    channel_names = {
        "AE":  "Ancient Earth Cinema",
        "GIA": "The Global Intel Analyst",
        "BF":  "The AI Bible Forensic"
    }
    ch_name    = channel_names.get(channel, channel)
    remaining  = rotation_threshold - videos_in_rotation
    date_str   = datetime.now().strftime("%A %d %B %Y")

    video_cards = "".join([
        _video_card(v, i+1, job_id, channel)
        for i, v in enumerate(top_videos[:5])
    ])

    subject = f"{channel} — Pick Your Competitor Video | {rotation_name} | {date_str}"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto">
  <div style="background:#0a1628;padding:24px;border-radius:8px 8px 0 0">
    <div style="color:#fff;font-size:22px;font-weight:bold">{ch_name}</div>
    <div style="color:#94a3b8;font-size:14px">Checkpoint 1 — Select Competitor Video</div>
  </div>
  
  <div style="background:#f0f4ff;padding:16px 24px;border-bottom:1px solid #ddd">
    <span style="font-weight:bold">Rotation:</span> R{["Ocean Monsters","Extinction Forensics","Ice Age Giants","Geological Record","Deep Weird","Strategic Geography","Alliance Fractures","Energy as Weapon","Miscalculation Autopsies","Theater Deep Analysis","Nephilim Giants Archaeology","Fallen Angels Enoch","Giants Smithsonian Cover-Up","Solomon Temple Architecture","Ancient Civilisations"].index(rotation_name)+1 if rotation_name in ["Ocean Monsters","Extinction Forensics","Ice Age Giants","Geological Record","Deep Weird","Strategic Geography","Alliance Fractures","Energy as Weapon","Miscalculation Autopsies","Theater Deep Analysis","Nephilim Giants Archaeology","Fallen Angels Enoch","Giants Smithsonian Cover-Up","Solomon Temple Architecture","Ancient Civilisations"] else "?"} — {rotation_name} &nbsp;·&nbsp; 
    <span style="font-weight:bold">Progress:</span> Video {videos_in_rotation+1} of {rotation_threshold} &nbsp;·&nbsp;
    <span style="font-weight:bold">Remaining:</span> {remaining-1} more after this
  </div>

  <div style="padding:24px">
    <p style="color:#444;margin-bottom:8px">
      Choose one video to base today's script on. Each video's angle and format 
      will shape the entire script. Click <strong>SELECT THIS VIDEO →</strong> then 
      complete the GitHub Actions form.
    </p>
    <p style="font-size:12px;color:#888;background:#fff3cd;padding:8px 12px;border-radius:4px">
      Job ID: <strong>{job_id}</strong> — you will need this in the GitHub form
    </p>
    
    {video_cards}
    
    <div style="margin-top:24px;padding:16px;background:#f9f9f9;border-radius:6px;font-size:13px;color:#666">
      <strong>How to select:</strong> Click the green button above → 
      Opens GitHub Actions → Click "Run workflow" → Enter job_id, video URL, and video title → Click "Run workflow"
    </div>
  </div>
</div>"""

    return _send(subject, html)


def send_checkpoint2(
    channel: str,
    rotation_name: str,
    job_id: str,
    script_text: str,
    word_count: int,
    competitor_title: str,
    competitor_url: str,
    ab_titles: list[str]
) -> dict:
    """Send Checkpoint 2 — script approval email."""
    channel_names = {"AE": "Ancient Earth Cinema", "GIA": "The Global Intel Analyst", "BF": "The AI Bible Forensic"}
    ch_name = channel_names.get(channel, channel)

    # Estimate video length at 0.85x TTS speed
    estimated_mins = round(word_count / (127 * 0.85), 1)

    dispatch_approve = f"https://github.com/{GITHUB_REPO}/actions/workflows/stage3_documents.yml"

    titles_html = "".join([
        f'<div style="padding:8px 12px;background:#f0f9ff;border-left:3px solid #3b82f6;margin:8px 0;font-size:14px">'
        f'<strong>Title {i+1}:</strong> {t}</div>'
        for i, t in enumerate(ab_titles)
    ])

    # Format script for email (first 800 words)
    script_preview = " ".join(script_text.split()[:800])
    if len(script_text.split()) > 800:
        script_preview += "...\n\n[Full script continues...]"

    subject = f"{channel} — Script Ready for Approval | {rotation_name} | {ab_titles[0][:50] if ab_titles else 'Review Script'}"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto">
  <div style="background:#0a1628;padding:24px;border-radius:8px 8px 0 0">
    <div style="color:#fff;font-size:22px;font-weight:bold">{ch_name}</div>
    <div style="color:#94a3b8;font-size:14px">Checkpoint 2 — Script Approval</div>
  </div>

  <div style="background:#f0f4ff;padding:16px 24px;border-bottom:1px solid #ddd">
    <strong>Based on:</strong> <a href="{competitor_url}">{competitor_title}</a><br>
    <strong>Word count:</strong> {word_count} words &nbsp;·&nbsp; 
    <strong>Est. length:</strong> ~{estimated_mins} min at 0.85x TTS
  </div>

  <div style="padding:24px">
    <h3 style="margin-top:0">Proposed AB Test Titles</h3>
    {titles_html}

    <h3>Script</h3>
    <div style="background:#f9f9f9;border:1px solid #ddd;border-radius:6px;padding:20px;
                font-size:14px;line-height:1.7;white-space:pre-wrap;max-height:600px;overflow-y:auto">
{script_preview}
    </div>

    <div style="margin-top:24px;display:flex;gap:16px;flex-wrap:wrap">
      <a href="{dispatch_approve}" target="_blank"
         style="background:#16a34a;color:#fff;padding:12px 24px;border-radius:6px;
                text-decoration:none;font-weight:bold;font-size:15px">
        ✓ APPROVE — START PRODUCTION
      </a>
      <a href="{dispatch_approve}" target="_blank"
         style="background:#d97706;color:#fff;padding:12px 24px;border-radius:6px;
                text-decoration:none;font-weight:bold;font-size:15px">
        ↺ REGENERATE SCRIPT
      </a>
    </div>
    <p style="font-size:12px;color:#888;margin-top:12px">
      Job ID: <strong>{job_id}</strong> — select action: <em>approve</em> or <em>regenerate</em>
    </p>
  </div>
</div>"""

    return _send(subject, html)


def send_reference_images(
    channel: str,
    job_id: str,
    video_title: str,
    missing_refs: list,
    new_characters: list = None
) -> dict:
    """Send Email B — missing reference images + new character sheet notifications."""
    channel_names = {"AE": "Ancient Earth Cinema", "GIA": "The Global Intel Analyst", "BF": "The AI Bible Forensic"}
    ch_name = channel_names.get(channel, channel)

    missing_count = len(missing_refs)
    new_char_count = len(new_characters or [])

    if missing_count == 0 and new_char_count == 0:
        return {"skipped": "no missing references"}

    # New character section
    new_char_html = ""
    if new_characters:
        new_char_html = f"""
<div style="background:#1e1b4b;border-radius:8px;padding:16px;margin-bottom:20px">
  <div style="color:#a5b4fc;font-size:13px;font-weight:bold;margin-bottom:12px">
    ⚡ {new_char_count} NEW CHARACTER{'S' if new_char_count > 1 else ''} DETECTED
  </div>
  <p style="color:#c7d2fe;font-size:12px;margin-bottom:12px">
    These characters appear in this video but have no reference sheet yet.
    Generate the 4-view character sheet FIRST, then the composite reference.
    After uploading both, the storyboard prompts for affected scenes will update automatically.
  </p>"""

        for char in new_characters:
            name       = char.get("name", "")
            scenes     = char.get("scenes_featuring", [])
            sheet_prompt  = char.get("character_sheet_prompt", "")
            sheet_file    = char.get("filename", "")
            comp_prompt   = char.get("composite_prompt", "")
            comp_file     = char.get("composite_filename", "")

            new_char_html += f"""
  <div style="border:1px solid #4338ca;border-radius:6px;padding:14px;margin:10px 0;background:#0f0e24">
    <div style="color:#818cf8;font-size:12px;font-weight:bold;margin-bottom:6px">
      NEW: {name.upper()} — appears in scenes {', '.join(str(s) for s in scenes[:8])}{'...' if len(scenes) > 8 else ''}
    </div>
    <div style="color:#a5b4fc;font-size:11px;font-weight:bold;margin:10px 0 4px">
      STEP 1 — Generate 4-view character reference sheet:
    </div>
    <div style="font-size:11px;color:#6366f1;margin-bottom:4px">Save as: <code style="color:#818cf8">{sheet_file}</code></div>
    <div style="background:#1e1b4b;border-radius:4px;padding:10px;margin:6px 0;color:#c7d2fe;font-size:10px;font-family:monospace;white-space:pre-wrap;word-break:break-word">{sheet_prompt[:600]}{'...' if len(sheet_prompt) > 600 else ''}</div>
    <div style="color:#a5b4fc;font-size:11px;font-weight:bold;margin:10px 0 4px">
      STEP 2 — Generate scene composite reference:
    </div>
    <div style="font-size:11px;color:#6366f1;margin-bottom:4px">Save as: <code style="color:#818cf8">{comp_file}</code></div>
    <div style="background:#1e1b4b;border-radius:4px;padding:10px;margin:6px 0;color:#c7d2fe;font-size:10px;font-family:monospace;white-space:pre-wrap;word-break:break-word">{comp_prompt[:400]}{'...' if len(comp_prompt) > 400 else ''}</div>
    <div style="color:#6ee7b7;font-size:11px;margin-top:8px">
      ✓ After uploading both images, the storyboard prompts for {len(scenes)} scene{'s' if len(scenes) > 1 else ''} will update automatically.
    </div>
  </div>"""

        new_char_html += "</div>"

    # Standard missing refs section
    ref_cards = ""
    for ref in missing_refs:
        if ref.get("is_new_character"):
            continue  # already shown in new character section
        scene_num  = ref.get("scene_number", "?")
        scene_text = ref.get("scene_text", "")[:80]
        ref_id     = ref.get("reference_id", "")
        filename   = ref.get("filename", f"{ref_id}.jpg")
        upload_to  = ref.get("upload_to", "Reference-Images")
        prompt     = ref.get("gpt_image_prompt", "")

        ref_cards += f"""
<div style="border:1px solid #fcd34d;border-radius:8px;padding:16px;margin:12px 0;background:#fffbeb">
  <div style="font-size:11px;color:#92400e;font-weight:bold">SCENE {scene_num} — MISSING REFERENCE</div>
  <div style="font-size:13px;color:#555;margin:4px 0 8px">{scene_text}...</div>
  <div style="font-size:12px;margin-bottom:6px">
    <strong>Save as:</strong> <code>{filename}</code><br>
    <strong>Upload to:</strong> {upload_to} / Google Drive
  </div>
  <div style="background:#1e1b4b;border-radius:4px;padding:12px;margin-top:8px">
    <div style="color:#a5b4fc;font-size:10px;margin-bottom:6px">GPT Image 2 prompt:</div>
    <div style="color:#e0e7ff;font-size:11px;font-family:monospace;white-space:pre-wrap;word-break:break-word">{prompt[:500]}{'...' if len(prompt) > 500 else ''}</div>
  </div>
</div>"""

    total_count = missing_count + new_char_count
    subject = f"{channel} — {total_count} Reference Image{'s' if total_count > 1 else ''} Needed | {video_title[:40]}"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto">
  <div style="background:#92400e;padding:24px;border-radius:8px 8px 0 0">
    <div style="color:#fff;font-size:20px;font-weight:bold">{ch_name}</div>
    <div style="color:#fde68a;font-size:14px">Reference Images Needed Before Production</div>
  </div>
  <div style="padding:24px">
    <p>Generate each image using <strong>GPT Image 2 with thinking mode enabled</strong>.
    Save with the exact filename. Upload to Google Drive. Then approve the script.</p>
    {new_char_html}
    {ref_cards if ref_cards.strip() else ''}
    <div style="margin-top:20px;padding:12px;background:#f0fdf4;border-radius:6px;font-size:13px">
      After generating and uploading all images, return to the Script Approval email and click APPROVE.
    </div>
  </div>
</div>"""

    return _send(subject, html)


def send_documents(
    channel: str,
    job_id: str,
    video_title: str,
    rotation_name: str,
    drive_folder_url: str,
    doc_paths: dict
) -> dict:
    """Send documents delivery email with attached Word docs."""
    channel_names = {"AE": "Ancient Earth Cinema", "GIA": "The Global Intel Analyst", "BF": "The AI Bible Forensic"}
    ch_name = channel_names.get(channel, channel)

    dispatch_ready = f"https://github.com/{GITHUB_REPO}/actions/workflows/stage4_assembly.yml"

    # Build file attachments
    import base64
    attachments = []
    doc_labels = {
        "doc1":  "Doc 1 — Full Scene Brief",
        "doc2":  "Doc 2 — Image Prompts (NBP)",
        "doc3a": "Doc 3A — Meta AI Video Prompts",
        "doc3b": "Doc 3B — VEO3.1 Video Prompts",
        "doc3c": "Doc 3C — Grok Aurora Video Prompts"
    }

    for key, label in doc_labels.items():
        path = doc_paths.get(key)
        if path:
            from pathlib import Path
            p = Path(path)
            if p.exists():
                content = base64.b64encode(p.read_bytes()).decode()
                attachments.append({
                    "filename": p.name,
                    "content":  content
                })

    subject = f"{channel} — 5 Production Documents Ready | {video_title[:50]}"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto">
  <div style="background:#0a1628;padding:24px;border-radius:8px 8px 0 0">
    <div style="color:#fff;font-size:20px;font-weight:bold">{ch_name}</div>
    <div style="color:#94a3b8;font-size:14px">5 Production Documents Ready</div>
  </div>

  <div style="padding:24px">
    <h3 style="margin-top:0">{video_title}</h3>
    <p><strong>Rotation:</strong> {rotation_name}</p>

    <h3>Your 5 Documents (attached)</h3>
    <ul style="line-height:2">
      <li><strong>Doc 1</strong> — Full scene brief: narration + all prompts per scene</li>
      <li><strong>Doc 2</strong> — Image prompts for VEO Automation extension (NBP)</li>
      <li><strong>Doc 3A</strong> — Video prompts for Meta AI (Auto Meta extension)</li>
      <li><strong>Doc 3B</strong> — Video prompts for Google Flow VEO3.1</li>
      <li><strong>Doc 3C</strong> — Video prompts for Grok Aurora (6s or 10s per scene)</li>
    </ul>

    <h3>Upload Folder</h3>
    <div style="background:#f0f9ff;padding:12px;border-radius:6px;margin-bottom:16px">
      <a href="{drive_folder_url}" style="color:#2563eb">{drive_folder_url}</a><br>
      <div style="font-size:12px;color:#666;margin-top:6px">
        Upload to <strong>images/</strong> subfolder: 001_image.jpg through N_image.jpg<br>
        Upload to <strong>videos/</strong> subfolder: 001_video.mp4 through N_video.mp4<br>
        Files must be named with 3-digit prefix (001, 002, 003...) for correct assembly order.
      </div>
    </div>

    <h3>When assets are ready</h3>
    <a href="{dispatch_ready}" target="_blank"
       style="background:#7c3aed;color:#fff;padding:12px 24px;border-radius:6px;
              text-decoration:none;font-weight:bold;font-size:15px">
      ✓ ASSETS READY — START ASSEMBLY
    </a>
    <p style="font-size:12px;color:#888;margin-top:12px">
      Job ID: <strong>{job_id}</strong><br>
      In GitHub: enter job_id and the Google Drive folder URL above.
    </p>
  </div>
</div>"""

    return _send(subject, html, attachments if attachments else None)


def send_delivery(
    channel: str,
    rotation_name: str,
    videos_in_rotation: int,
    rotation_threshold: int,
    video_title: str,
    studio_url: str,
    ab_titles: list[str],
    thumbnails: list[dict],
    description: str,
    tags: list[str],
    hashtags: list[str],
    chapters: str,
    next_rotation: Optional[str] = None
) -> dict:
    """Send final delivery email with everything needed for YouTube upload."""
    channel_names = {"AE": "Ancient Earth Cinema", "GIA": "The Global Intel Analyst", "BF": "The AI Bible Forensic"}
    ch_name = channel_names.get(channel, channel)

    rotation_switch_warning = ""
    if videos_in_rotation >= rotation_threshold - 1:
        rotation_switch_warning = f"""
<div style="background:#fef3c7;border:1px solid #d97706;border-radius:6px;padding:12px;margin:16px 0">
  <strong>⚡ Rotation Switch Incoming</strong><br>
  This is video {videos_in_rotation+1} of {rotation_threshold}. 
  The next run will switch to: <strong>{next_rotation or 'next rotation'}</strong>
</div>"""

    # AB test titles section
    titles_html = ""
    for i, title in enumerate(ab_titles[:3]):
        variant = chr(65 + i)  # A, B, C
        auto_note = " (auto-set on upload)" if i == 0 else " (add manually in YouTube Studio)"
        titles_html += f"""
<div style="border:1px solid #ddd;border-radius:6px;padding:12px;margin:8px 0">
  <div style="font-size:11px;color:#888;font-weight:bold">VARIANT {variant}{auto_note}</div>
  <div style="font-size:15px;font-weight:bold;color:#1a1a1a;margin-top:4px">{title}</div>
</div>"""

    tags_str = ", ".join(tags[:15])
    hashtags_str = " ".join(hashtags[:15])

    subject = f"✅ {channel} — Video Ready | {rotation_name} | Video {videos_in_rotation+1}/{rotation_threshold}"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto">
  <div style="background:#16a34a;padding:24px;border-radius:8px 8px 0 0">
    <div style="color:#fff;font-size:22px;font-weight:bold">✅ {ch_name}</div>
    <div style="color:#dcfce7;font-size:14px">Video Ready — Review and Publish</div>
  </div>

  <div style="background:#f0fdf4;padding:16px 24px;border-bottom:1px solid #ddd">
    <strong>Rotation:</strong> {rotation_name} &nbsp;·&nbsp;
    <strong>Progress:</strong> Video {videos_in_rotation+1} of {rotation_threshold}
  </div>

  {rotation_switch_warning}

  <div style="padding:24px">
    <h3 style="margin-top:0">Video Uploaded — Unlisted</h3>
    <a href="{studio_url}" target="_blank"
       style="background:#0a1628;color:#fff;padding:12px 24px;border-radius:6px;
              text-decoration:none;font-weight:bold;font-size:15px">
      Open YouTube Studio →
    </a>

    <h3 style="margin-top:24px">AB Test — Titles</h3>
    {titles_html}

    <h3>YouTube Description</h3>
    <div style="background:#f9f9f9;border:1px solid #ddd;border-radius:6px;padding:16px;
                font-size:13px;white-space:pre-wrap;max-height:400px;overflow-y:auto">{description}</div>

    <h3>Timestamp Chapters</h3>
    <div style="background:#f9f9f9;border:1px solid #ddd;border-radius:6px;padding:16px;
                font-family:monospace;font-size:13px;white-space:pre-wrap">{chapters}</div>

    <h3>Tags</h3>
    <div style="background:#f9f9f9;border:1px solid #ddd;border-radius:6px;padding:12px;font-size:13px">
      {tags_str}
    </div>

    <h3>Hashtags</h3>
    <div style="background:#f9f9f9;border:1px solid #ddd;border-radius:6px;padding:12px;font-size:13px">
      {hashtags_str}
    </div>
  </div>
</div>"""

    return _send(subject, html)


def send_rotation_change(
    channel: str,
    old_rotation: str,
    new_rotation: str
) -> dict:
    """Send rotation change notification."""
    channel_names = {"AE": "Ancient Earth Cinema", "GIA": "The Global Intel Analyst", "BF": "The AI Bible Forensic"}
    ch_name = channel_names.get(channel, channel)
    subject = f"{channel} — Rotation Switch: {old_rotation} → {new_rotation}"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
  <div style="background:#4f46e5;padding:24px;border-radius:8px">
    <div style="color:#fff;font-size:20px;font-weight:bold">{ch_name}</div>
    <div style="color:#e0e7ff;font-size:14px;margin-top:8px">
      Completed 15 videos in <strong>{old_rotation}</strong>.<br>
      Starting next run: <strong>{new_rotation}</strong>
    </div>
  </div>
</div>"""

    return _send(subject, html)
