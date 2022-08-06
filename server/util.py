#!/usr/bin/env python3

import b2sdk.v2 as b2
import settings
import mariadb
import sys

def UTIL_delete(vid_id):
    global db
    global db_cur

    if vid_id is None or vid_id == "":
        print("Video ID not given!")
        return

    b2_api = b2.B2Api(b2.InMemoryAccountInfo())
    b2_api.authorize_account("production", settings.B2_APP_KEY_ID, settings.B2_APP_KEY)
    b2_bucket = b2_api.get_bucket_by_name(settings.B2_BUCKET)

    b2_bucket.get_file_info_by_name(f"{vid_id}.mp4").delete()
    b2_bucket.get_file_info_by_name(f"{vid_id}.jpg").delete()

    db_cur.execute("UPDATE videos SET video_url=NULL, thumb_url=NULL, rendered_by=NULL WHERE id=?", (vid_id,))
    db.commit()

def UTIL_clear_queue(worker_name):
    global db
    global db_cur
    db_cur.execute("UPDATE videos SET rendered_by=NULL WHERE rendered_by=? AND video_url IS NULL", (worker_name,))
    db.commit()

db_args = {
    "user": settings.DB_USER,
    "password": settings.DB_PASS,
    "host": settings.DB_HOST,
    "port": settings.DB_PORT,
    "database": settings.DB_DATABASE,
}

def list_utils():
    print("Available utils:")
    for name in globals():
        if name.startswith("UTIL_"):
            code = globals()[name].__code__
            args = [ f"<{arg}>" for arg in code.co_varnames[:code.co_argcount] ]
            arg_list = " ".join(args)
            print(f"  {name[5:]} {arg_list}")
    sys.exit(1)

if len(sys.argv) < 2:
    print("No util specified")
    list_utils()

name = sys.argv[1]
args = sys.argv[2:]

if ("UTIL_" + name) not in globals():
    print("No such util")
    list_utils()

db = mariadb.connect(**db_args)
db_cur = db.cursor()

globals()["UTIL_" + name](*args)

db_cur.close()
db.close()
