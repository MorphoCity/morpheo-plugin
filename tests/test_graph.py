# -*- coding: utf-8 -*-
""" Test graph consistency
"""


def test_isolated_vertices(conn):
    """ Test that there is no isolated vertices
    """
    rows = conn.execute("SELECT OGC_FID FROM vertices WHERE degree=0").fetchall()
    rows = [r[0] for r in rows]
    assert len(rows)==0, "Found isolated vertices {}".format(rows)


def test_endpoints_vertices_for_edges(conn):
    """ Test that there no null start/end vertices for edges
    """
    rows = conn.execute("SELECT OGC_FID FROM edges WHERE START_VTX IS NULL OR END_VTX IS NULL").fetchall()
    rows = [r[0] for r in rows]
    assert len(rows)==0, "Found edges with null start/end vertices {}".format(rows)
