# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
import store
import search as S

conn = store.connect()
try:
    rows = S.search(conn, "ximeng", limit=5)
    print("OK rows:", len(rows))
except Exception as e:
    import traceback
    traceback.print_exc()
