"""
main.py — Master orchestration for the YouTube automation system.
"""

import argparse
import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.state import (
    load_state, save_state, get_channel_state,
    check_and_advance_rotation, create_job, get_job,
    update_job, complete_job, get_rotation_status
)
from src.email_sender import (
    send_checkpoint1, send_checkpoint2, send_reference_images,
    send_documents, send_delivery, send_rotation_change
)


# ─────────────────────────────────────────────────────────────
# Stage 1
# ─────────────────────────────────────────────────────────────

def stage1_research(channel: str):
    print(f"\n{'='*60}")
    print(f"STAGE 1 — RESEARCH — {channel}")
    print(f"{'='*60}\n")

    from src.research import run_research

    switched, new_rotation = check_and_advance_rotation(channel)
    ch_state = get_channel_state(channel)

    if switched:
        rotations = ch_state["rotations"]
        cur = ch_state["current_rotation"]
        prev_num = str(cur - 1 if cur > 1 else len(rotations))
        old_rotation = rotations.get(prev_num, "Previous Rotation")
        send_rotation_change(channel, old_rotation, new_rotation)

    rotation_status = get_rotation_status(channel)
    print(f"[Main] Rotation: {rotation_status['rotation_name']}")
    print(f"[Main] Videos: {rotation_status['videos_in_rotation']}/{rotation_status['rotation_threshold']}")

    top_videos = run_research(channel)

    if not top_videos:
        print("[Main] WARNING: Research returned no videos.")

    job_id = create_job(channel, 1, {
        "top_videos":        top_videos,
        "rotation_name":     rotation_status["rotation_name"],
        "videos_in_rotation": rotation_status["videos_in_rotation"]
    })
    print(f"[Main] Job created: {job_id}")

    send_checkpoint1(
        channel=channel,
        rotation_name=rotation_status["rotation_name"],
        videos_in_rotation=rotation_status["videos_in_rotation"],
        rotation_threshold=rotation_status["rotation_threshold"],
        top_videos=top_videos,
        job_id=job_id
    )
    print(f"[Main] Stage 1 complete. Job ID: {job_id}")


# ─────────────────────────────────────────────────────────────
# Stage 2
# ─────────────────────────────────────────────────────────────

def stage2_script(channel: str, video_url: str, video_title: str, job_id: str):
    print(f"\n{'='*60}")
    print(f"STAGE 2 — SCRIPT GENERATION — {channel}")
    print(f"{'='*60}\n")

    from src.subscribr import full_script_pipeline
    from src.references import analyse_script_references, get_missing_references, get_new_characters

    ch_state     = get_channel_state(channel)
    rotation_name = ch_state["rotation_name"]
    channel_id   = ch_state["subscribr_channel_id"]
    channel_name = ch_state["channel_name"]

    # Ensure job exists — create from parameters if Stage 1 push didn't persist it
    try:
        get_job(job_id)
        print(f"[Main] Found existing job: {job_id}")
    except ValueError:
        print(f"[Main] Job {job_id} not found — creating from parameters")
        state = load_state()
        if "pending_jobs" not in state:
            state["pending_jobs"] = {}
        state["pending_jobs"][job_id] = {
            "channel":    channel,
            "stage":      2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "competitor_video_url":   video_url,
                "competitor_video_title": video_title,
                "rotation_name":          rotation_name
            }
        }
        save_state(state)

    update_job(job_id, {
        "competitor_video_url":   video_url,
        "competitor_video_title": video_title,
        "competitor_video_id":    _extract_video_id(video_url)
    })

    # Run Subscribr script pipeline
    result = full_script_pipeline(
        channel_id=channel_id,
        rotation_name=rotation_name,
        channel_name=channel_name,
        video_url=video_url,
        video_title=video_title
    )

    update_job(job_id, {
        "script_id":   result["script_id"],
        "idea_id":     result["idea_id"],
        "script_text": result["script_text"],
        "ab_titles":   result["ab_titles"],
        "word_count":  result["word_count"]
    })

    # Analyse references
    print("[Main] Analysing reference images...")
    ref_analysis = analyse_script_references(result["script_text"], channel)
    missing_refs = get_missing_references(ref_analysis)
    new_chars    = get_new_characters(ref_analysis)

    update_job(job_id, {
        "ref_analysis":  ref_analysis,
        "missing_refs":  missing_refs,
        "new_characters": new_chars
    })

    # Send Checkpoint 2
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

    # Send Email B if references are missing
    if missing_refs or new_chars:
        send_reference_images(
            channel=channel,
            job_id=job_id,
            video_title=result["ab_titles"][0] if result["ab_titles"] else "New Video",
            missing_refs=missing_refs,
            new_characters=new_chars
        )
        print(f"[Main] {len(missing_refs)} missing refs, {len(new_chars)} new characters notified")
    else:
        print("[Main] All references covered")

    print(f"[Main] Stage 2 complete. Job ID: {job_id}")


# ─────────────────────────────────────────────────────────────
# Stage 3
# ─────────────────────────────────────────────────────────────

def stage3_documents(channel: str, job_id: str, action: str):
    print(f"\n{'='*60}")
    print(f"STAGE 3 — DOCUMENTS — {channel} ({action})")
    print(f"{'='*60}\n")

    if action == "regenerate":
        job = get_job(job_id)
        data = job["data"]
        stage2_script(
            channel=channel,
            video_url=data.get("competitor_video_url", ""),
            video_title=data.get("competitor_video_title", ""),
            job_id=job_id
        )
        return

    from src.tts import (
        generate_tts_with_timestamps, generate_music,
        assign_scene_timings, extract_chapter_timings,
        format_chapters_for_description
    )
    from src.documents import build_all_documents, generate_metadata
    from src.subscribr import generate_thumbnails
    from src.drive import create_video_folder, upload_file

    job      = get_job(job_id)
    data     = job["data"]
    ch_state = get_channel_state(channel)

    script_text = data["script_text"]
    ab_titles   = data["ab_titles"]
    idea_id     = data.get("idea_id", "")
    voice_id    = ch_state["voice_id"]
    video_title = ab_titles[0] if ab_titles else "Documentary Video"

    work_dir = Path(tempfile.mkdtemp()) / f"{channel}_{job_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    # TTS
    tts_result    = generate_tts_with_timestamps(script_text, voice_id, work_dir)
    scene_timings = assign_scene_timings(script_text, tts_result["timestamps_path"])
    chapter_timings = extract_chapter_timings(script_text, scene_timings)
    chapters_text   = format_chapters_for_description(chapter_timings)

    # Music
    music_prompt = "Cinematic documentary score, orchestral, building tension, completely instrumental, no vocals"
    music_path   = generate_music(tts_result["total_duration_seconds"], music_prompt, work_dir)

    # Metadata
    metadata = generate_metadata(
        script_text=script_text,
        ab_titles=ab_titles,
        channel=channel,
        rotation_name=ch_state["rotation_name"],
        chapter_timings=chapter_timings
    )

    # Thumbnails
    thumbnails = generate_thumbnails(
        channel_id=ch_state["subscribr_channel_id"],
        idea_id=idea_id,
        competitor_thumbnail_url=data.get("competitor_thumbnail_url")
    )

    # Drive folder
    base_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    drive_folders  = create_video_folder(channel, video_title, base_folder_id)

    # Documents
    docs_result = build_all_documents(
        script_text=script_text,
        channel=channel,
        video_title=video_title,
        scene_timings=scene_timings,
        output_dir=work_dir / "documents"
    )

    # Upload audio/SRT/music to Drive
    for path in [tts_result["audio_path"], tts_result["srt_path"]]:
        if path and Path(path).exists():
            upload_file(path, drive_folders["output_folder_id"])
    if music_path and Path(music_path).exists():
        upload_file(music_path, drive_folders["output_folder_id"])

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

    send_documents(
        channel=channel,
        job_id=job_id,
        video_title=video_title,
        rotation_name=ch_state["rotation_name"],
        drive_folder_url=drive_folders["video_folder_url"],
        doc_paths=docs_result
    )
    print(f"[Main] Stage 3 complete. Drive: {drive_folders['video_folder_url']}")


# ─────────────────────────────────────────────────────────────
# Stage 4
# ─────────────────────────────────────────────────────────────

def stage4_assembly(channel: str, job_id: str, drive_folder_url: str):
    print(f"\n{'='*60}")
    print(f"STAGE 4 — ASSEMBLY — {channel}")
    print(f"{'='*60}\n")

    from src.drive import (
        get_folder_id_from_url, list_folder_files,
        download_assets_folder, upload_file,
        get_or_create_folder, upload_final_video, download_file
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

    # Resolve folder IDs
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

    # Download video clips
    video_clips = download_assets_folder(videos_folder_id, str(work_dir / "videos"), "videos")
    if not video_clips:
        raise RuntimeError("[Main] No video clips in Drive videos/ folder")

    # Download audio assets
    audio_path = None
    music_path = None
    srt_path   = None

    for f in list_folder_files(output_folder_id):
        name = f["name"]
        local = str(work_dir / name)
        if "narration" in name.lower() and name.endswith(".wav") and not audio_path:
            download_file(f["id"], local)
            audio_path = local
        elif name.endswith(".mp3") and not music_path:
            download_file(f["id"], local)
            music_path = local
        elif name.endswith(".srt") and not srt_path:
            download_file(f["id"], local)
            srt_path = local

    if not audio_path:
        raise RuntimeError("[Main] Narration audio not found in Drive output/ folder")
    if not srt_path:
        raise RuntimeError("[Main] SRT captions not found in Drive output/ folder")

    # Assemble
    safe_filename = sanitize_filename(ab_titles[0] if ab_titles else video_title)
    output_path   = str(work_dir / safe_filename)

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

    # Download thumbnails
    thumbnail_paths = []
    for thumb in thumbnails[:3]:
        url = thumb.get("url", "")
        if url:
            local = str(work_dir / f"thumbnail_{thumb['variant']}.jpg")
            if download_thumbnail_from_url(url, local):
                thumbnail_paths.append({
                    "variant": thumb["variant"],
                    "label":   thumb.get("label", ""),
                    "path":    local
                })

    # Upload to YouTube
    thumb_a = thumbnail_paths[0]["path"] if thumbnail_paths else None
    yt_result = upload_video(
        video_path=output_path,
        title=ab_titles[0] if ab_titles else video_title,
        description=metadata["description"],
        tags=metadata["tags"],
        channel=channel,
        thumbnail_path=thumb_a
    )
    print(f"[Main] Uploaded: {yt_result['video_id']}")

    # Upload final video to Drive
    upload_final_video(output_path, output_folder_id)

    # Record in memory
    try:
        from src.memory import record_produced_video
        record_produced_video(
            channel=channel,
            youtube_video_id=yt_result["video_id"],
            competitor_channel_name=data.get("competitor_channel_name", ""),
            competitor_video_url=data.get("competitor_video_url", ""),
            angle=data.get("subscribr_angle", ""),
            format_type=data.get("subscribr_format", "Documentary"),
            rotation_name=ch_state["rotation_name"],
            title=video_title
        )
    except Exception as e:
        print(f"[Main] Memory record skipped: {e}")

    # Mark complete
    complete_job(job_id, channel)
    ch_state = get_channel_state(channel)

    # Delivery email
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
    print(f"[Main] Stage 4 complete. Studio: {yt_result['studio_url']}")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _extract_video_id(url: str) -> str:
    if "watch?v=" in url:
        return url.split("v=")[1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage",        type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--channel",      required=True, choices=["AE", "GIA", "BF"])
    parser.add_argument("--video-url",    default="")
    parser.add_argument("--video-title",  default="")
    parser.add_argument("--job-id",       default="")
    parser.add_argument("--action",       default="approve", choices=["approve", "regenerate"])
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
