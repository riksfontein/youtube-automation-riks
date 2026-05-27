"""
main.py — Master orchestration for the YouTube automation system.

Usage:
  python src/main.py --stage 1 --channel AE
  python src/main.py --stage 2 --channel AE --video-url URL --video-title TITLE --job-id ID
  python src/main.py --stage 3 --channel AE --job-id ID --action approve
  python src/main.py --stage 4 --channel AE --job-id ID --drive-folder URL
"""

import argparse
import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.state import (
    load_state, get_channel_state, check_and_advance_rotation,
    create_job, get_job, update_job, complete_job,
    get_rotation_status, get_rotation_keywords
)
from src.email_sender import (
    send_checkpoint1, send_checkpoint2, send_reference_images,
    send_documents, send_delivery, send_rotation_change
)


def stage1_research(channel: str):
    """
    Stage 1: Research competitors + send Checkpoint 1 email.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 1 — RESEARCH — {channel}")
    print(f"{'='*60}\n")

    from src.research import run_research

    # Check for rotation switch
    switched, new_rotation = check_and_advance_rotation(channel)
    ch_state = get_channel_state(channel)

    if switched:
        print(f"[Main] Rotation switched to: {new_rotation}")
        # Get previous rotation name for the notification
        rotations = ch_state["rotations"]
        prev_num = str(ch_state["current_rotation"] - 1 or len(rotations))
        old_rotation = rotations.get(prev_num, "Previous Rotation")
        send_rotation_change(channel, old_rotation, new_rotation)

    rotation_status = get_rotation_status(channel)
    print(f"[Main] Rotation: {rotation_status['rotation_name']}")
    print(f"[Main] Videos: {rotation_status['videos_in_rotation']}/{rotation_status['rotation_threshold']}")

    # Run three-layer research
    top_videos = run_research(channel)

    if not top_videos:
        print("[Main] WARNING: No videos found in research. Check API connections.")
        top_videos = []  # Send empty email as notification

    # Create job
    job_id = create_job(channel, 1, {
        "top_videos": top_videos,
        "rotation_name": rotation_status["rotation_name"],
        "videos_in_rotation": rotation_status["videos_in_rotation"]
    })

    print(f"[Main] Job created: {job_id}")

    # Send Checkpoint 1 email
    send_checkpoint1(
        channel=channel,
        rotation_name=rotation_status["rotation_name"],
        videos_in_rotation=rotation_status["videos_in_rotation"],
        rotation_threshold=rotation_status["rotation_threshold"],
        top_videos=top_videos,
        job_id=job_id
    )

    print(f"\n[Main] Stage 1 complete. Checkpoint 1 email sent to info@croki.store")
    print(f"[Main] Waiting for video selection... Job ID: {job_id}")


def stage2_script(channel: str, video_url: str, video_title: str, job_id: str):
    """
    Stage 2: Generate script from selected competitor video.
    Sends Checkpoint 2 (script approval) + Email B (reference images).
    """
    print(f"\n{'='*60}")
    print(f"STAGE 2 — SCRIPT GENERATION — {channel}")
    print(f"{'='*60}\n")

    from src.subscribr import full_script_pipeline
    from src.references import analyse_script_references, get_missing_references

    ch_state = get_channel_state(channel)
    rotation_name = ch_state["rotation_name"]
    channel_id = ch_state["subscribr_channel_id"]
    channel_name = ch_state["channel_name"]

    # Store competitor video info in job
    update_job(job_id, {
        "competitor_video_url":   video_url,
        "competitor_video_title": video_title,
        "competitor_video_id":    _extract_video_id_from_url(video_url)
    })

    # Run Subscribr pipeline
    result = full_script_pipeline(
        channel_id=channel_id,
        rotation_name=rotation_name,
        channel_name=channel_name,
        video_url=video_url,
        video_title=video_title
    )

    # Store script in job
    update_job(job_id, {
        "script_id":   result["script_id"],
        "idea_id":     result["idea_id"],
        "script_text": result["script_text"],
        "ab_titles":   result["ab_titles"],
        "word_count":  result["word_count"]
    })

    # Analyse reference images
    print("[Main] Analysing reference image requirements...")
    ref_analysis = analyse_script_references(result["script_text"], channel)
    missing_refs = get_missing_references(ref_analysis)

    update_job(job_id, {
        "ref_analysis": ref_analysis,
        "missing_refs": missing_refs
    })

    # Send Checkpoint 2 (script approval)
    send_checkpoint2(
        channel=channel,
        rotation_name=rotation_name,
        job_id=job_id,
        script_text=result["script_text"],
        word_count=result["word_count"],
        competitor_title=video_title,
        competitor_url=video_url,
        ab_titles=result["ab_titles"]
    )

    # Send Email B (reference images) simultaneously
    if missing_refs:
        send_reference_images(
            channel=channel,
            job_id=job_id,
            video_title=result["ab_titles"][0] if result["ab_titles"] else "New Video",
            missing_refs=missing_refs
        )
        print(f"[Main] {len(missing_refs)} missing references notified")
    else:
        print("[Main] All references covered — no reference email needed")

    print(f"\n[Main] Stage 2 complete. Checkpoint 2 + reference emails sent.")
    print(f"[Main] Waiting for script approval...")


def stage3_documents(channel: str, job_id: str, action: str):
    """
    Stage 3: Generate 5 production documents.
    Triggered by script approval.
    If action is 'regenerate', reruns script generation.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 3 — DOCUMENT GENERATION — {channel} ({action})")
    print(f"{'='*60}\n")

    if action == "regenerate":
        # Re-run stage 2 with same video
        job = get_job(job_id)
        data = job["data"]
        stage2_script(
            channel=channel,
            video_url=data["competitor_video_url"],
            video_title=data["competitor_video_title"],
            job_id=job_id
        )
        return

    from src.tts import (
        generate_tts_with_timestamps, generate_music,
        assign_scene_timings, extract_chapter_timings, format_chapters_for_description
    )
    from src.documents import build_all_documents, generate_metadata
    from src.subscribr import generate_thumbnails
    from src.drive import create_video_folder, upload_file

    job    = get_job(job_id)
    data   = job["data"]
    ch_state = get_channel_state(channel)

    script_text = data["script_text"]
    ab_titles   = data["ab_titles"]
    idea_id     = data.get("idea_id")
    voice_id    = ch_state["voice_id"]

    video_title = ab_titles[0] if ab_titles else "Documentary Video"

    # Work directory
    work_dir = Path(tempfile.mkdtemp()) / f"{channel}_{job_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Generate TTS with timestamps
    print("[Main] Generating TTS narration...")
    tts_result = generate_tts_with_timestamps(script_text, voice_id, work_dir)

    # Assign scene timings
    scene_timings = assign_scene_timings(script_text, tts_result["timestamps_path"])
    chapter_timings = extract_chapter_timings(script_text, scene_timings)
    chapters_text = format_chapters_for_description(chapter_timings)

    # Generate music
    music_prompt = ch_state.get("music_prompt", "Cinematic documentary score, orchestral, building tension, completely instrumental, absolutely no vocals, no singing, no choir")
    music_path = generate_music(tts_result["total_duration_seconds"], music_prompt, work_dir)

    # Generate metadata (description, tags, hashtags)
    metadata = generate_metadata(
        script_text=script_text,
        ab_titles=ab_titles,
        channel=channel,
        rotation_name=ch_state["rotation_name"],
        chapter_timings=chapter_timings
    )

    # Generate thumbnails
    print("[Main] Generating thumbnails...")
    competitor_thumbnail_url = data.get("competitor_thumbnail_url")
    thumbnails = generate_thumbnails(
        channel_id=ch_state["subscribr_channel_id"],
        idea_id=idea_id,
        competitor_thumbnail_url=competitor_thumbnail_url
    )

    # Build Google Drive folder
    base_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    drive_folders = create_video_folder(channel, video_title, base_folder_id)

    # Build all 5 documents
    docs_result = build_all_documents(
        script_text=script_text,
        channel=channel,
        video_title=video_title,
        scene_timings=scene_timings,
        output_dir=work_dir / "documents"
    )

    # Upload audio and SRT to Drive
    upload_file(tts_result["audio_path"], drive_folders["output_folder_id"])
    upload_file(tts_result["srt_path"],   drive_folders["output_folder_id"])
    if music_path:
        upload_file(music_path, drive_folders["output_folder_id"])

    # Store everything in job
    update_job(job_id, {
        "video_title":            video_title,
        "scene_timings":          scene_timings,
        "chapter_timings":        chapter_timings,
        "chapters_text":          chapters_text,
        "metadata":               metadata,
        "thumbnails":             thumbnails,
        "audio_path":             tts_result["audio_path"],
        "srt_path":               tts_result["srt_path"],
        "music_path":             music_path,
        "total_duration_seconds": tts_result["total_duration_seconds"],
        "drive_folders":          drive_folders,
        "doc_paths":              docs_result
    })

    # Send documents email with attachments
    send_documents(
        channel=channel,
        job_id=job_id,
        video_title=video_title,
        rotation_name=ch_state["rotation_name"],
        drive_folder_url=drive_folders["video_folder_url"],
        doc_paths=docs_result
    )

    print(f"\n[Main] Stage 3 complete. 5 documents sent to info@croki.store")
    print(f"[Main] Drive folder: {drive_folders['video_folder_url']}")
    print(f"[Main] Waiting for assets (images + videos)...")


def stage4_assembly(channel: str, job_id: str, drive_folder_url: str):
    """
    Stage 4: Download assets, assemble video, upload to YouTube, send delivery email.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 4 — ASSEMBLY & UPLOAD — {channel}")
    print(f"{'='*60}\n")

    from src.drive import (
        get_folder_id_from_url, list_folder_files, download_assets_folder,
        upload_file, get_or_create_folder, upload_final_video
    )
    from src.assembly import assemble_video, sanitize_filename
    from src.youtube import upload_video, download_thumbnail_from_url

    job      = get_job(job_id)
    data     = job["data"]
    ch_state = get_channel_state(channel)

    video_title     = data["video_title"]
    ab_titles       = data["ab_titles"]
    metadata        = data["metadata"]
    thumbnails      = data.get("thumbnails", [])
    scene_timings   = data["scene_timings"]
    drive_folders   = data["drive_folders"]
    chapters_text   = data["chapters_text"]

    work_dir = Path(tempfile.mkdtemp()) / f"{channel}_{job_id}_assembly"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Get folder IDs from the provided URL (or from saved state)
    if drive_folder_url:
        video_folder_id = get_folder_id_from_url(drive_folder_url)
        if video_folder_id:
            images_folder_id = get_or_create_folder("images", video_folder_id)
            videos_folder_id = get_or_create_folder("videos", video_folder_id)
            output_folder_id = get_or_create_folder("output", video_folder_id)
        else:
            images_folder_id = drive_folders.get("images_folder_id")
            videos_folder_id = drive_folders.get("videos_folder_id")
            output_folder_id = drive_folders.get("output_folder_id")
    else:
        images_folder_id = drive_folders.get("images_folder_id")
        videos_folder_id = drive_folders.get("videos_folder_id")
        output_folder_id = drive_folders.get("output_folder_id")

    # Download video clips from Drive
    print("[Main] Downloading video clips from Google Drive...")
    video_clips = download_assets_folder(
        videos_folder_id,
        str(work_dir / "videos"),
        asset_type="videos"
    )

    if not video_clips:
        raise RuntimeError("[Main] No video clips found in Drive videos/ folder")

    print(f"[Main] Downloaded {len(video_clips)} video clips")

    # Download audio from Drive (already generated in Stage 3)
    print("[Main] Downloading audio assets...")
    audio_files = list_folder_files(output_folder_id, ".wav")
    music_files = list_folder_files(output_folder_id, ".mp3")
    srt_files   = list_folder_files(output_folder_id, ".srt")

    audio_path = None
    music_path = None
    srt_path   = None

    for f in audio_files:
        if "narration" in f["name"].lower():
            audio_path = str(work_dir / f["name"])
            from src.drive import download_file
            download_file(f["id"], audio_path)
            break

    for f in music_files:
        music_path = str(work_dir / f["name"])
        from src.drive import download_file
        download_file(f["id"], music_path)
        break

    for f in srt_files:
        srt_path = str(work_dir / f["name"])
        from src.drive import download_file
        download_file(f["id"], srt_path)
        break

    if not audio_path:
        raise RuntimeError("[Main] Narration audio not found in Drive output/ folder")
    if not srt_path:
        raise RuntimeError("[Main] Captions SRT not found in Drive output/ folder")

    # Assemble final video
    safe_filename = sanitize_filename(ab_titles[0] if ab_titles else video_title)
    output_path = str(work_dir / safe_filename)

    assemble_video(
        video_clips=video_clips,
        audio_path=audio_path,
        music_path=music_path,
        srt_path=srt_path,
        scene_timings=scene_timings,
        output_path=output_path,
        channel=channel,
        work_dir=str(work_dir / "work")
    )

    print(f"[Main] Assembly complete: {output_path}")

    # Download thumbnails
    thumbnail_paths = []
    for thumb in thumbnails[:3]:
        url = thumb.get("url", "")
        if url:
            local_path = str(work_dir / f"thumbnail_{thumb['variant']}.jpg")
            result = download_thumbnail_from_url(url, local_path)
            if result:
                thumbnail_paths.append({
                    "variant": thumb["variant"],
                    "label":   thumb["label"],
                    "path":    result
                })

    # Upload to YouTube (unlisted, Thumbnail A auto-set)
    print("[Main] Uploading to YouTube...")
    thumb_a_path = thumbnail_paths[0]["path"] if thumbnail_paths else None

    yt_result = upload_video(
        video_path=output_path,
        title=ab_titles[0] if ab_titles else video_title,
        description=metadata["description"],
        tags=metadata["tags"],
        channel=channel,
        thumbnail_path=thumb_a_path
    )

    print(f"[Main] YouTube upload complete: {yt_result['video_id']}")

    # Upload final video to Drive output/ folder as backup
    upload_final_video(output_path, output_folder_id)

    # Mark job complete (increments rotation counter)
    complete_job(job_id, channel)
    ch_state = get_channel_state(channel)  # reload updated state

    # Send delivery email
    send_delivery(
        channel=channel,
        rotation_name=ch_state["rotation_name"],
        videos_in_rotation=ch_state["videos_in_rotation"],
        rotation_threshold=ch_state["rotation_threshold"],
        video_title=video_title,
        studio_url=yt_result["studio_url"],
        ab_titles=ab_titles,
        thumbnails=thumbnail_paths,
        description=metadata["description"],
        tags=metadata["tags"],
        hashtags=metadata["hashtags"],
        chapters=chapters_text,
        next_rotation=ch_state.get("rotations", {}).get(
            str((ch_state["current_rotation"] % len(ch_state["rotations"])) + 1)
        )
    )

    print(f"\n[Main] Stage 4 complete.")
    print(f"[Main] YouTube Studio: {yt_result['studio_url']}")
    print(f"[Main] Delivery email sent to info@croki.store")


def _extract_video_id_from_url(url: str) -> str:
    if "youtube.com/watch?v=" in url:
        return url.split("v=")[1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Automation System")
    parser.add_argument("--stage", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--channel", required=True, choices=["AE", "GIA", "BF"])
    parser.add_argument("--video-url",   default="")
    parser.add_argument("--video-title", default="")
    parser.add_argument("--job-id",      default="")
    parser.add_argument("--action",      default="approve", choices=["approve", "regenerate"])
    parser.add_argument("--drive-folder", default="")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"YouTube Automation — Stage {args.stage} — Channel {args.channel}")
    print(f"{'='*60}")

    if args.stage == 1:
        stage1_research(args.channel)
    elif args.stage == 2:
        if not args.video_url:
            print("ERROR: --video-url required for stage 2")
            sys.exit(1)
        stage2_script(args.channel, args.video_url, args.video_title, args.job_id)
    elif args.stage == 3:
        if not args.job_id:
            print("ERROR: --job-id required for stage 3")
            sys.exit(1)
        stage3_documents(args.channel, args.job_id, args.action)
    elif args.stage == 4:
        if not args.job_id:
            print("ERROR: --job-id required for stage 4")
            sys.exit(1)
        stage4_assembly(args.channel, args.job_id, args.drive_folder)
