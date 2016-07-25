# -*- coding: utf-8 -*-
""" Test graph consistency
"""


def test_isolated_vertices(conn):
    """ Test that there is no isolated vertices
    """
    rows = conn.execute("SELECT OGC_FID FROM vertices WHERE degree=0").fetchall()
    rows = [r[0] for r in rows]
    assert len(rows)==0, "Found isolated vertices {}".format(rows)
