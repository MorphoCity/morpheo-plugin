""" Test places
"""




def test_vertices_has_place(conn):
    """ Test that all vertices have a corresponding place
    """
    count = conn.execute("SELECT Count(DISTINCT VERTEX) FROM place_vtx").fetchone()[0]
    nvtx  = conn.execute("SELECT Count(1) FROM vertices").fetchone()[0]
    assert count == nvtx  


def test_no_null_place_edges(conn):
    """ Test that there is no null place_edges geometry
    """
    count = conn.execute("SELECT Count(*) FROM place_edges WHERE GEOMETRY IS NULL").fetchone()[0]
    assert count == 0

