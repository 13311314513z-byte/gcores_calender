# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
import search as S

w, p = S._extra_where(None, None, None, None, None)
print("extra_w:", repr(w), "params:", p)
q = "ximeng"
base_w = "e.is_published=1 AND e.owner_type='gcores'"
extra_w = w
like = "%" + q + "%"
sql = (
    "SELECT e.*, c.name AS category_name, a.title AS album_title "
    "FROM episodes e "
    "LEFT JOIN categories c ON c.id=e.category_id "
    "LEFT JOIN albums a ON a.id=e.album_id "
    f"WHERE {base_w} AND (e.title LIKE ? OR e.subtitle LIKE ? "
    "OR e.page_desc LIKE ? OR c.name LIKE ?){extra_w} "
    "ORDER BY e.published_date DESC, e.id DESC LIMIT ?"
)
print("SQL:", sql)
