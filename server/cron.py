#!/usr/bin/env python3

# this whole file is a bit of a hack lol

import settings
from common import *
import mariadb
import datetime
import sys
from contextlib import closing
from decimal import Decimal
import requests

def get_keyvalue(key):
    db_cur.execute("SELECT value FROM misc_data WHERE key_=?", (key,))
    return db_cur.fetchone()[0]

def set_keyvalue(key, val):
    db_cur.execute("INSERT INTO misc_data (key_, value) VALUES (?, ?) ON DUPLICATE KEY UPDATE value=?", (key, val, val))
    db.commit()

def update_changelog(now, changelog, last_handled):
    ready = last_handled is None

    new_last = None

    for idx, entry in enumerate(changelog):
        changelog_id = int(entry["id"])

        if idx % 1000 == 0:
            print(f"On changelog {idx}")

        if not ready and changelog_id >= last_handled:
            ready = True
            if changelog_id == last_handled:
                continue

        if not ready:
            continue

        # This sometimes happens and I have no fucking clue why?????
        if entry["post_rank"] is None:
            continue # TODO what does this mean?

        if entry["time_gained"] is None:
            continue

        timestamp = datetime.datetime.strptime(entry["time_gained"], "%Y-%m-%d %H:%M:%S")

        #if now - timestamp < datetime.timedelta(hours=settings.WAIT_RENDER_HOURS):
            # Too new!
            #continue

        if entry["pending"] == "1" or entry["banned"] == "1":
            # Skip pending times
            continue

        new_last = changelog_id

        # Double check; do we already have this changelog somehow?
        db_cur.execute("SELECT 1 FROM videos WHERE id=?", (changelog_id,))
        if db_cur.fetchone():
            continue # TODO we should probably complain, this shouldn"t happen
        db_cur.execute("SELECT 1 FROM changelogs_errored WHERE id=?", (changelog_id,))
        if db_cur.fetchone():
            continue

        post_rank = int(entry["post_rank"])

        # We store *all* times above the threshold, even if we don"t
        # need to render them, to make changelog calculations accurate
        if post_rank <= settings.RANK_THRESHOLD:
            pre_rank = entry["pre_rank"] if entry["pre_rank"] is not None else 501 # HACKHACK
            map_id = entry["mapid"]
            profile_id = entry["profile_number"]
            player_name = entry["player_name"]
            chamber_name = entry["chamberName"]
            score = int(entry["score"])
            comment = entry["note"]
            #should_render = entry["hasDemo"] != "0" and entry["youtubeID"] is None
            should_render = entry["hasDemo"] and entry["hasDemo"] != "0" # might be bool or string
            if coop and row["date"] < datetime.datetime(2021, 2, 19) + datetime.timedelta(weeks=3):
                should_render = False # pre-update coop demo

            db_cur.execute("UPDATE videos SET cur_rank = IF(cur_rank+1 > 500, NULL, cur_rank+1) WHERE map=? AND cur_rank <= ? AND cur_rank >= ? AND time != ?", (map_id, pre_rank, post_rank, Decimal(score) / 100))
            db_cur.execute("UPDATE videos SET obsoleted = TRUE, cur_rank = NULL, should_render = FALSE WHERE map=? AND user=?", (map_id, profile_id))

            db_cur.execute("INSERT INTO users (id, name) VALUES (?, ?) ON DUPLICATE KEY UPDATE name=?", (profile_id, player_name, player_name))
            #db_cur.execute("INSERT INTO maps (id, name) VALUES (?, ?) ON DUPLICATE KEY UPDATE name=?", (map_id, chamber_name, chamber_name))
            db_cur.execute("""
                INSERT INTO videos (
                    id,
                    user,
                    map,
                    time,
                    cur_rank,
                    orig_rank,
                    comment,
                    date,
                    video_url,
                    views,
                    obsoleted,
                    should_render
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, FALSE, ?)
            """, (
                changelog_id,
                profile_id,
                map_id,
                Decimal(score) / 100,
                post_rank,
                post_rank,
                comment,
                timestamp,
                should_render,
            ))

        db.commit()

    if new_last is not None:
        set_keyvalue("last_changelog", str(new_last))
        set_keyvalue("last_changelog_time", now.strftime("%Y-%m-%dT%H:%M:%SZ"))

def CRON_update_changelog_api():
    last_handled = int(get_keyvalue("last_changelog"))
    last_time = datetime.datetime.strptime(get_keyvalue("last_changelog_time"), "%Y-%m-%dT%H:%M:%SZ")
    
    now = datetime.datetime.now()

    days = (now - last_time).days + 1 #+ settings.WAIT_RENDER_DAYS

    changelog = requests.get(f"{settings.BOARDS_BASE}/changelog/json?maxDaysAgo={days}").json()

    if not changelog:
        pass # TODO error

    update_changelog(now, reversed(changelog), last_handled) # Reverse the changelog so we get the changes in order

def CRON_update_changelog_db(database):
    db_args = {
        "user": settings.DB_USER,
        "password": settings.DB_PASS,
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "database": database,
    }

    with closing(mariadb.connect(**db_args)) as iverb_db:
        with closing(iverb_db.cursor()) as iverb_db_cur:
            # We can"t be sure how old this database is; take the last
            # changelog as the time
            iverb_db_cur.execute("SELECT time_gained FROM changelog ORDER BY time_gained DESC LIMIT 1")

            timestamp, = iverb_db_cur.fetchone()

            iverb_db_cur.execute("""
                SELECT
                    changelog.id,
                    map_id AS mapid,
                    changelog.profile_number,
                    pre_rank,
                    post_rank,
                    DATE_FORMAT(time_gained, "%Y-%m-%d %H:%m:%s") AS time_gained,
                    has_demo AS hasDemo,
                    youtube_id AS youtubeID,
                    score,
                    note,
                    pending,
                    changelog.banned,
                    IFNULL(usersnew.boardname, usersnew.steamname) AS player_name,
                    maps.name AS chamberName
                FROM
                    changelog
                    INNER JOIN usersnew ON (changelog.profile_number = usersnew.profile_number)
                    INNER JOIN maps ON (changelog.map_id = maps.steam_id)
                WHERE
                    changelog.banned = 0
                    AND usersnew.banned = 0
                ORDER BY time_gained ASC
            """)

            update_changelog(timestamp, fetch_dict(iverb_db_cur), None)

def fetch_map_data(map_id):
    data = requests.get(f"{settings.BOARDS_BASE}/chamber/{map_id}/json").json()

    if not data:
        pass # TODO error

    return data

def CRON_resync_ranks():
    maps = {}

    db_cur.execute("SELECT * FROM videos WHERE obsoleted=FALSE")

    for row in fetch_dict(db_cur, True):
        changelog_id = row["id"]
        map_id = row["map"]
        user_id = row["user"]

        db_cur.execute("SELECT coop FROM maps WHERE id=?", (map_id,))
        coop = db_cur.fetchall()[0][0]

        if map_id not in maps:
            maps[map_id] = fetch_map_data(map_id)

        map_data = maps[map_id]

        obsoleted = str(user_id) not in map_data or int(map_data[str(user_id)]["scoreData"]["changelogId"]) != changelog_id

        if obsoleted:
            print(f"Obsoleting changelog {changelog_id}")
            db_cur.execute("UPDATE videos SET cur_rank=NULL, obsoleted=TRUE, should_render=FALSE where id=?", (changelog_id,))
        else:
            score_data = map_data[str(user_id)]["scoreData"]

            rank = int(score_data["playerRank"])
            if row["cur_rank"] != rank:
                print(f"Updating rank for changelog {changelog_id}")
                db_cur.execute("UPDATE videos SET cur_rank=? WHERE id=?", (rank, changelog_id))

            #should_render = score_data["hasDemo"] != "0" and score_data["youtubeID"] is None
            should_render = score_data["hasDemo"] != "0"
            if coop and row["date"] < datetime.datetime(2021, 2, 19) + datetime.timedelta(weeks=3):
                should_render = False # pre-update coop demo

            if should_render != row["should_render"]:
                print(f"Updating should_render for changelog {changelog_id}")
                db_cur.execute("UPDATE videos SET should_render=? WHERE id=?", (should_render, changelog_id))

    db.commit()

def CRON_fix_obsolete():
    maps = {}

    db_cur.execute("SELECT * FROM videos")

    for row in fetch_dict(db_cur, True):
        changelog_id = row["id"]
        map_id = row["map"]
        user_id = row["user"]

        if map_id not in maps:
            maps[map_id] = fetch_map_data(map_id)

        map_data = maps[map_id]

        obsoleted = str(user_id) not in map_data or int(map_data[str(user_id)]["scoreData"]["changelogId"]) != changelog_id

        if obsoleted != row["obsoleted"]:
            print(f"Correcting obsoleted for changelog {changelog_id}")
            db_cur.execute("UPDATE videos SET obsoleted=? where id=?", (obsoleted, changelog_id))

    db.commit()

def CRON_resync_names():
    db_cur.execute("SELECT * FROM users")

    for row in fetch_dict(db_cur, True):
        user_id = row["id"]
        name = row["name"]

        data = requests.get(f"{settings.BOARDS_BASE}/profile/{user_id}/json").json()
        new_name = data["userData"]["displayName"]
        
        if name != new_name:
            print(f"Updating name for user {user_id} ({name} -> {new_name})")
            db_cur.execute("UPDATE users SET name=? WHERE id=?", (new_name, user_id))

    db.commit()

db_args = {
    "user": settings.DB_USER,
    "password": settings.DB_PASS,
    "host": settings.DB_HOST,
    "port": settings.DB_PORT,
    "database": settings.DB_DATABASE,
}

def list_jobs():
    print("Available jobs:")
    for name in globals():
        if name.startswith("CRON_"):
            code = globals()[name].__code__
            args = [ f"<{arg}>" for arg in code.co_varnames[:code.co_argcount] ]
            arg_list = " ".join(args)
            print(f"  {name[5:]} {arg_list}")
    sys.exit(1)

if len(sys.argv) < 2:
    print("No job specified")
    list_jobs()

name = sys.argv[1]
args = sys.argv[2:]

if ("CRON_" + name) not in globals():
    print("No such job")
    list_jobs()

db = mariadb.connect(**db_args)
db_cur = db.cursor()

globals()["CRON_" + name](*args)

db_cur.close()
db.close()
