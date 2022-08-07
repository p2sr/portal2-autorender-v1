#!/usr/bin/env python3

from flask import Flask, request, abort, make_response, redirect, send_file
import mariadb
from functools import wraps
from contextlib import closing
import b2sdk.v2 as b2
import re
from fuzzywuzzy import fuzz
import operator
import subprocess
from pathlib import Path
import os
import requests

import settings
from common import *

app = Flask(__name__, static_folder="static", static_url_path="")

def with_db(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        db_args = {
            "user": settings.DB_USER,
            "password": settings.DB_PASS,
            "host": settings.DB_HOST,
            "port": settings.DB_PORT,
            "database": settings.DB_DATABASE,
        }

        with closing(mariadb.connect(**db_args)) as db:
            with closing(db.cursor()) as db_cur:
                return f(db, db_cur, *args, **kwargs)

    return wrapped

def try_match(query_words, words):
    best = 0

    for possible_match in zip(*[query_words[i:] for i in range(len(words))]):
        val = fuzz.ratio(" ".join(words), " ".join(possible_match))
        if best is None or best < val:
            best = val

    return best

def recent_videos(db, db_cur):
    db_cur.execute("""
        SELECT
            videos.id                   AS id,
            users.name                  AS user,
            CONVERT(videos.user, CHAR)  AS user_id,
            maps.name                   AS map,
            videos.map                  AS map_id,
            FLOOR(videos.time * 100)    AS time,
            videos.cur_rank             AS cur_rank,
            videos.orig_rank            AS orig_rank,
            videos.comment              AS comment,
            videos.views                AS views,
            videos.obsoleted            AS obsoleted,
            DATE_FORMAT(videos.date, "%Y-%m-%dT%TZ") AS date
        FROM
            videos
            INNER JOIN users ON (videos.user = users.id)
            INNER JOIN maps ON (videos.map = maps.id)
        WHERE
            video_url IS NOT NULL
        ORDER BY date DESC
        LIMIT 30
    """)

    return { "results": list(fetch_dict(db_cur, True)), "end": True }

@app.route("/api/v1/search", methods=["GET"])
@with_db
def search(db, db_cur):
    args = request.args

    if "q" not in args:
        abort(400) # Bad Request

    if args["q"].strip() == "":
        # Return recent videos rather than actual search results
        return recent_videos(db, db_cur)

    # Do some processing on the terms to convert to a format that SQL
    # will deal with better

    words = re.findall(r"\w+", args["q"].lower())

    # Step 0: if they"ve given an ID, try and parse it

    force_user_id, force_other_id = None, None

    for w in words.copy():
        try:
            x = int(w)
            if len(w) == 17:
                # user ID
                force_user_id = x
                words.remove(w)
            elif len(w) > 4:
                # changelog or map ID
                force_other_id = x
                words.remove(w)
        except ValueError:
            pass

    # Step 1: try to parse out a map name

    maps = []

    db_cur.execute("SELECT id, name FROM maps")
    for map_id, name in db_cur:
        map_words = re.findall(r"\w+", name.lower())
        maps.append((map_id, map_words))

        # people don"t tend to write out the word "propulsion", so just
        # accept "prop"
        if "propulsion" in map_words:
            words_new = map_words.copy()
            words_new[words_new.index("propulsion")] = "prop"
            maps.append((map_id, words_new))

    map_confidences = {}

    for map_id, map_words in maps:
        val = try_match(words, map_words)

        if val > 50:
            if map_id not in map_confidences:
                map_confidences[map_id] = val
            elif val > map_confidences[map_id]:
                map_confidences[map_id] = val

    # Step 2: try to parse out a rank

    rank = None

    for i, w in enumerate(words):
        next_word = None if len(words) <= i + 1 else words[i + 1]
        if w == "wr":
            rank = 1
            break
        elif next_word is not None and fuzz.ratio(f"{w} {next_word}", "world record") > 90:
            rank = 1
            break
        elif re.match(r"^\d+(?:st|nd|rd|th)$", w):
            rank = int(w[:-2])
            break
        elif re.match(r"^\d+$", w) and next_word in ["st","nd","rd","th"]:
            rank = int(w)
            break

    # Step 3: runner name

    user_confidences = {}

    db_cur.execute("SELECT id, name FROM users")
    for user_id, name in db_cur:
        user_words = re.findall(r"\w+", name.lower())
        val = try_match(words, user_words)

        if val > 50:
            if user_id not in user_confidences:
                user_confidences[user_id] = val
            elif val > user_confidences[user_id]:
                user_confidences[user_id] = val

    map_id = max(map_confidences.items(), key=operator.itemgetter(1)) if len(map_confidences) > 0 else None
    user_id = max(user_confidences.items(), key=operator.itemgetter(1)) if len(user_confidences) > 0 else None

    try:
        start = int(args["start"]) if "start" in args else 0
    except ValueError:
        start = 0

    db_cur.execute("""
        SELECT
            videos.id                   AS id,
            users.name                  AS user,
            CONVERT(videos.user, CHAR)  AS user_id,
            maps.name                   AS map,
            videos.map                  AS map_id,
            FLOOR(videos.time * 100)    AS time,
            videos.cur_rank             AS cur_rank,
            videos.orig_rank            AS orig_rank,
            videos.comment              AS comment,
            videos.views                AS views,
            videos.obsoleted            AS obsoleted,
            DATE_FORMAT(videos.date, "%Y-%m-%dT%TZ") AS date,
            (
                IF(videos.user = ?, ?, 0) +
                IF(videos.map = ?, ?, 0) +
                IF(videos.cur_rank = ?, 1.0, IF(videos.orig_rank = ?, 0.6, 0)) +
                videos.views * 0.005 +
                IF(videos.user = ?, 10.0, 0) +
                IF(videos.id = ?, 20.0, 0) +
                IF(videos.map = ?, 10.0, 0)
            ) AS rank
        FROM
            videos
            INNER JOIN users ON (videos.user = users.id)
            INNER JOIN maps ON (videos.map = maps.id)
        WHERE video_url IS NOT NULL
        HAVING rank > 0.5
        ORDER BY rank DESC, videos.date DESC
        LIMIT ?, 21
    """, (user_id[0] if user_id else None, user_id[1] / 100 if user_id else None, map_id[0] if map_id else None, map_id[1] / 100 if map_id else None, rank, rank, force_user_id, force_other_id, force_other_id, start))

    results = []

    for row in fetch_dict(db_cur):
        del row["rank"]
        results.append(row)

    end = True

    if len(results) == 21:
        results = results[:-1]
        end = False

    return { "results": results, "end": end }

@app.route("/api/v1/video/<int:vid_id>/info", methods=["GET"])
@with_db
def video_info(db, db_cur, vid_id):
    db_cur.execute("""
        SELECT
            videos.id                   AS id,
            users.name                  AS user,
            CONVERT(videos.user, CHAR)  AS user_id,
            maps.name                   AS map,
            videos.map                  AS map_id,
            FLOOR(videos.time * 100)    AS time,
            videos.cur_rank             AS cur_rank,
            videos.orig_rank            AS orig_rank,
            videos.comment              AS comment,
            videos.views                AS views,
            videos.obsoleted            AS obsoleted,
            DATE_FORMAT(videos.date, "%Y-%m-%dT%TZ") AS date
        FROM
            videos
            INNER JOIN users ON (videos.user = users.id)
            INNER JOIN maps ON (videos.map = maps.id)
        WHERE
            video_url IS NOT NULL AND
            videos.id=?
    """, (vid_id,))

    row = next(fetch_dict(db_cur), None)

    if not row:
        abort(404) # Not Found
    
    return row

@app.route("/api/v1/video/<int:vid_id>/thumb", methods=["GET"])
@with_db
def video_thumb(db, db_cur, vid_id):
    db_cur.execute("SELECT thumb_url FROM videos WHERE video_url IS NOT NULL AND id=?", (vid_id,))

    row = db_cur.fetchone()

    if not row:
        abort(404) # Not Found

    thumb_url, = row

    if not thumb_url:
        abort(404) # Not Found

    return redirect(thumb_url, code=307)

@app.route("/api/v1/video/<int:vid_id>/video", methods=["GET"])
@with_db
def video_video(db, db_cur, vid_id):
    db_cur.execute("SELECT video_url FROM videos WHERE video_url IS NOT NULL AND id=?", (vid_id,))
    row = db_cur.fetchone()
    
    if not row:
        abort(404) # Not Found

    video_url, = row

    return redirect(video_url, code=307)

@app.route("/api/v1/video/<int:vid_id>/view", methods=["POST"])
@with_db
def video_view(db, db_cur, vid_id):
    # TODO: ratelimit!
    db_cur.execute("UPDATE videos SET views = views + 1 WHERE video_url IS NOT NULL AND id=?", (vid_id,))
    db.commit()

    return {}

def authenticated(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if request.authorization:
            if request.authorization.username in settings.AUTHS:
                if settings.AUTHS[request.authorization.username] == request.authorization.password:
                    return f(request.authorization.username, *args, **kwargs)

        return ("Unauthorized", 401, {
            "WWW-Authenticate": 'Basic realm="Access to video upload endpoint"'
        })

    return wrapped

@app.route("/api/v1/upload/pending", methods=["GET"])
@with_db
@authenticated
def upload_pending(username, db, db_cur):
    #db_cur.execute("UPDATE videos SET rendered_by=NULL where rendered_by=?", (username,))
    # XXX: change this to ASC once we've rendered the backlog
    db_cur.execute("SELECT id FROM videos WHERE video_url IS NULL AND rendered_by IS NULL AND should_render = TRUE ORDER BY date DESC LIMIT 3")
    ids = db_cur.fetchall()
    ids = list(map(lambda r: r[0], ids))
    for dem in ids:
        db_cur.execute("UPDATE videos SET rendered_by=? WHERE id=?", (username, dem))
    db.commit()
    demos = []
    for dem in ids:
        db_cur.execute("SELECT time FROM videos WHERE id=?", (dem,))
        time, = db_cur.fetchone()
        demos.append({ "id": dem, "time": str(time) })
    return {"demos": demos}

@app.route("/api/v1/upload/video/<int:vid_id>", methods=["PUT"])
@with_db
@authenticated
def upload_video(username, db, db_cur, vid_id):
    db_cur.execute("SELECT 1 FROM videos WHERE video_url IS NULL AND should_render = TRUE AND id=?", (vid_id,))
    if not db_cur.fetchone():
        abort(404) # Not Found

    if len(request.data) > 500_000_000: # 500 MB
        abort(413) # Payload Too Large

    Path(settings.TMP_DIR).mkdir(parents=True, exist_ok=True)

    with open(f"{settings.TMP_DIR}/{vid_id}.mp4", "wb") as f:
        f.write(request.data)

    proc = subprocess.Popen([
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        f"{settings.TMP_DIR}/{vid_id}.mp4",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out, _ = proc.communicate()

    if proc.returncode != 0:
        os.remove(f"{settings.TMP_DIR}/{vid_id}.mp4")
        abort(500) # Internal Server Error

    video_duration = float(out)

    proc = subprocess.Popen([
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i", f"{settings.TMP_DIR}/{vid_id}.mp4",
        "-vframes", "1",
        "-an",
        "-s", "960x540",
        "-ss", str(video_duration / 2),
        f"{settings.TMP_DIR}/{vid_id}.jpg",
    ])

    proc.communicate()

    if proc.returncode != 0:
        os.remove(f"{settings.TMP_DIR}/{vid_id}.mp4")
        os.remove(f"{settings.TMP_DIR}/{vid_id}.jpg")
        abort(500) # Internal Server Error

    b2_api = b2.B2Api(b2.InMemoryAccountInfo())
    b2_api.authorize_account("production", settings.B2_APP_KEY_ID, settings.B2_APP_KEY)
    b2_bucket = b2_api.get_bucket_by_name(settings.B2_BUCKET)

    b2_bucket.upload_local_file(f"{settings.TMP_DIR}/{vid_id}.mp4", f"{vid_id}.mp4")
    vid_url = b2_bucket.get_download_url(f"{vid_id}.mp4")

    b2_bucket.upload_local_file(f"{settings.TMP_DIR}/{vid_id}.jpg", f"{vid_id}.jpg")
    thumb_url = b2_bucket.get_download_url(f"{vid_id}.jpg")

    db_cur.execute("UPDATE videos SET views=0, video_url=?, thumb_url=? WHERE id=?", (vid_url, thumb_url, vid_id))
    db.commit()

    os.remove(f"{settings.TMP_DIR}/{vid_id}.mp4")
    os.remove(f"{settings.TMP_DIR}/{vid_id}.jpg")


    requests.post(
        "https://discord.com/api/webhooks/" + ...,
        params={
            "thread_id": "1005216644907409438",
        },
        json={
            "username": "Auto-Render",
            "content": f"https://autorender.portal2.sr/video.html?v={vid_id}",
        },
    )

    return {}


@app.route("/api/v1/upload/error", methods=["POST"])
@with_db
@authenticated
def upload_error(username, db, db_cur):
    content = request.get_json()

    for entry in content["demos"]:
        err_id = entry["id"]
        reason = entry["reason"]
        db_cur.execute("SELECT 1 FROM videos WHERE video_url IS NULL AND should_render = TRUE AND id=?", (err_id,))
        if db_cur.fetchone():
            db_cur.execute("DELETE FROM videos WHERE id=?", (err_id,))
            db_cur.execute("INSERT IGNORE INTO changelogs_errored (id, reason, error_date) VALUES (?, ?, NOW())", (err_id, reason))

    db.commit()

    return {}

@app.route("/video.html", methods=["GET"])
@with_db
def video_page(db, db_cur):
    if "v" not in request.args:
        abort(404)

    vid_id = request.args["v"]

    db_cur.execute("""
        SELECT
            videos.id                   AS vid_id,
            users.name                  AS user,
            maps.name                   AS map,
            videos.time                 AS time,
            videos.thumb_url            AS thumb_url,
            videos.video_url            AS video_url,
            videos.comment              AS comment
        FROM
            videos
            INNER JOIN users ON (videos.user = users.id)
            INNER JOIN maps ON (videos.map = maps.id)
        WHERE
            video_url IS NOT NULL AND
            videos.id=?
    """, (vid_id,))

    row = next(fetch_dict(db_cur), None)

    if not row:
        abort(404) # Not Found

    with open('./video_template.html', 'r') as f:
        page = f.read()

    comment = row["comment"] if row["comment"] is not None else ""
    comment = comment.replace('"', '&quot;')

    page = (page
        .replace("{vid_id}", str(row["vid_id"]))
        .replace("{user}", row["user"])
        .replace("{map}", row["map"])
        .replace("{time}", str(row["time"]))
        .replace("{comment}", comment)
        .replace("{thumb_url}", row["thumb_url"])
        .replace("{video_url}", row["video_url"])
        .replace("{url_base}", "https://autorender.portal2.sr"))

    return page

@app.route("/", methods=["GET"])
def root():
    return app.send_static_file("index.html")