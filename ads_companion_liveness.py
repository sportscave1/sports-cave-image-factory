"""Record authenticated browser contact independently of queue claim contention."""


def heartbeat(factory, token_hash, key):
    # A job/control transaction can lock the paired desktop row. Reading the
    # credential does not need that lock, and contact must survive a failed
    # claim transaction. Never run providers or claim work on this connection.
    with factory() as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout='500ms'")
        cur.execute("SET LOCAL statement_timeout='2500ms'")
        cur.execute('SELECT 1 FROM product_upload_desktop WHERE singleton AND token_hash=%s',
                    (token_hash,))
        if not cur.fetchone():
            raise PermissionError('The paired desktop credential is required.')
        cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,'true',now())
            ON CONFLICT(key) DO UPDATE SET updated_at=now()
            WHERE app_settings.updated_at<now()-interval '20 seconds'""", (key,))
