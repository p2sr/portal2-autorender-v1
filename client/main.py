#!/usr/bin/env python3

import settings
import requests
import asyncio
import os
from pathlib import Path
import subprocess
import shutil

# prevents a race condition that can make us try to double-render demos
g_uploading = set()

# the number of times the dummy demo has failed to render
g_failed_dummy = 0

def download_demo(demo_id):
    with requests.get(f"{settings.BOARDS_BASE}/getDemo?id={demo_id}", stream=True) as r:
        r.raise_for_status()
        with open(f"{settings.PORTAL2_DIR}/portal2/demos/{demo_id}.dem", "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

def get_demos_to_render():
    global g_uploading

    auth = requests.auth.HTTPBasicAuth(settings.API_UNAME, settings.API_PWORD)
    r = requests.get(f"{settings.API_BASE}/upload/pending", auth=auth)
    r.raise_for_status()

    demos = r.json()["demos"]
    demos = [dem for dem in demos if dem["id"] not in g_uploading]

    for dem in demos:
        dem_id = dem["id"]
        if not os.path.isfile(f"{settings.PORTAL2_DIR}/portal2/demos/{dem_id}.dem"):
            download_demo(dem_id)

    return demos

async def try_render(demos):
    global g_failed_dummy

    # delete all existing renders
    for item in os.listdir(f"{settings.PORTAL2_DIR}/portal2/demos"):
        if item.endswith(".dem.mp4"):
            try:
                os.remove(f"{settings.PORTAL2_DIR}/portal2/demos/{item}")
            except PermissionError:
                pass # let's just hope nothing breaks
    
    # total demo duration
    duration = 0.0

    # gen configs
    with open(f"{settings.PORTAL2_DIR}/portal2/cfg/autoexec.cfg", "w") as f:
        f.write("plugin_load sar\n")
        f.write("sar_fast_load_preset full\n")
        f.write("sar_disable_no_focus_sleep 1\n")
        f.write(f"exec {settings.RENDER_CFG}\n")

        for idx, dem in enumerate(demos):
            dem_id = dem["id"]
            f.write(f'sar_alias r_{idx} "playdemo demos/{dem_id}; sar_alias r_next r_{idx+1}"\n')
            duration += float(dem["time"])

        f.write(f'sar_alias r_{len(demos)} "playdemo demos/{settings.DUMMY_DEMO}; sar_alias r_next quit\n')

        f.write("sar_alias r_next r_0\n")
        f.write("sar_on_demo_stop r_next\n")
        f.write(f"playdemo demos/{settings.DUMMY_DEMO}\n")

    # the game can sometimes freeze, either just from bad luck or from dodgy
    # demos. this is the maximum time the game can be open before we give up and
    # kill it
    timeout = duration * settings.RENDER_TIMEOUT_FACTOR + settings.RENDER_TIMEOUT_BASE

    # do the render
    proc = await asyncio.subprocess.create_subprocess_exec(f"{settings.PORTAL2_DIR}/portal2.exe", "-game", "portal2", "-novid", "-vulkan", "-windowed", "-w", "1280", "-h", "720", "+mat_motion_blur_enabled", "0", cwd=settings.PORTAL2_DIR)
    try:
        await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        # timeout
        proc.kill()

    # this might help make sure file handles are properly closed? idk
    await asyncio.sleep(1)

    # check whether any renders happened at all
    if not os.path.exists(f"{settings.PORTAL2_DIR}/portal2/demos/{settings.DUMMY_DEMO}.dem.mp4"):
        g_failed_dummy += 1

    # if the dummy keeps failing, terminate
    if g_failed_dummy > 5:
        raise RuntimeError("Portal 2 crashed before playing any demos! Is the dummy demo corrupt?")

    # check which ones completed
    complete = []
    incomplete = []
    for dem in demos:
        dem_id = dem["id"]
        path = f"{settings.PORTAL2_DIR}/portal2/demos/{dem_id}.dem.mp4"
        if os.path.exists(path):
            # it exists; is the file valid?
            ff_proc = subprocess.Popen(["./ffprobe.exe", path])
            ff_proc.communicate()
            if ff_proc.returncode == 0:
                # it rendered successfully
                complete.append(dem)
                continue

        incomplete.append(dem)

    return complete, incomplete

def move_rendered_demo(demo):
    dem_id = demo["id"]
    Path(settings.RENDER_TMP_DIR).mkdir(parents=True, exist_ok=True)
    shutil.move(f"{settings.PORTAL2_DIR}/portal2/demos/{dem_id}.dem.mp4", f"{settings.RENDER_TMP_DIR}/{dem_id}.mp4")

async def render_maybe_corrupt(demo):
    complete, _ = await try_render([demo])
    if len(complete) == 1:
        # we successfully renderered the demo
        move_rendered_demo(demo)
        asyncio.create_task(upload_demo(demo))
        # try and make sure everything's been moved
        await asyncio.sleep(1)
    else:
        # that demo is definitely corrupt
        report_corrupt_demo(demo, "Render failed after 2 attempts")

async def render_many(demos):
    while len(demos) > 0:
        complete, incomplete = await try_render(demos)

        # move the completed renders elsewhere
        for demo in complete:
            move_rendered_demo(demo)
            dem_id = demo["id"]
            os.unlink(f"{settings.PORTAL2_DIR}/portal2/demos/{dem_id}.dem")
            asyncio.create_task(upload_demo(demo))

        # try and make sure everything's been moved
        await asyncio.sleep(1)

        # the first incomplete demo could be corrupt
        if len(incomplete) > 0:
            await render_maybe_corrupt(incomplete[0])
            dem_id = incomplete[0]["id"]
            os.unlink(f"{settings.PORTAL2_DIR}/portal2/demos/{dem_id}.dem")
            incomplete = incomplete[1:]

        # update our demo list and continue
        demos = incomplete

async def upload_demo(demo):
    global g_uploading

    dem_id = demo["id"]

    g_uploading |= { dem_id }

    # reencode video to improve size
    ff_proc = subprocess.Popen(["./ffmpeg.exe", "-i", f"{settings.RENDER_TMP_DIR}/{dem_id}.mp4", f"{settings.RENDER_TMP_DIR}/{dem_id}_reencoded.mp4"])
    ff_proc.communicate()
    if ff_proc.returncode != 0:
        print(f"Failed to re-encode {dem_id}! Using original render.")
        shutil.copy(f"{settings.RENDER_TMP_DIR}/{dem_id}.mp4", f"{settings.RENDER_TMP_DIR}/{dem_id}_reencoded.mp4")

    with open(f"{settings.RENDER_TMP_DIR}/{dem_id}_reencoded.mp4", "rb") as f:
        auth = requests.auth.HTTPBasicAuth(settings.API_UNAME, settings.API_PWORD)
        r = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.put(f"{settings.API_BASE}/upload/video/{dem_id}", auth=auth, data=f))
        if r.status_code != 200:
            print(f"Rendered demo {dem_id}, but failed to upload!")
            report_corrupt_demo(demo, f"Video upload failed with status {r.status_code}")

    os.unlink(f"{settings.RENDER_TMP_DIR}/{dem_id}.mp4")
    os.unlink(f"{settings.RENDER_TMP_DIR}/{dem_id}_reencoded.mp4")

    g_uploading.remove(dem_id)

def report_corrupt_demo(demo, reason):
    data = { "demos": [ { "id": demo["id"], "reason": reason } ] }

    auth = requests.auth.HTTPBasicAuth(settings.API_UNAME, settings.API_PWORD)
    r = requests.post(f"{settings.API_BASE}/upload/error", auth=auth, json=data)

async def main():
    global g_uploading
    while True:
        # if we're uploading a lot of demos, stop and wait for the
        # backlog to clear a bit
        while len(g_uploading) > 10:
            await asyncio.sleep(10)

        try:
            demos = get_demos_to_render()
        except requests.HTTPError:
            print("Failed to get demos to render! Assuming none.")
            demos = []

        if demos:
            # render em!
            print(f"Rendering {len(demos)} demos...")
            await render_many(demos)
            # wait a few seconds, to make sure all uploads have started
            await asyncio.sleep(5)
        else:
            # wait a while to prevent spamming requests
            print("No demos to render!")
            await asyncio.sleep(30)

asyncio.get_event_loop().run_until_complete(main())
