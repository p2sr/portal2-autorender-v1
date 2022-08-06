def fetch_dict(cursor, slurp=False):
    cols = [ col[0] for col in cursor.description ]
    if slurp:
        rows = cursor.fetchall()
        for row in rows:
            yield { col: val for col, val in zip(cols, row) }
    else:
        row = cursor.fetchone()
        while row:
            yield { col: val for col, val in zip(cols, row) }
            row = cursor.fetchone()
