""" Test places
"""




def test_vertices_has_place(conn):
    """ Test that all vertices have a corresponding place
    """
    count = conn.execute("SELECT Count(DISTINCT VERTEX) FROM place_vtx").fetchone()[0]
    nvtx  = conn.execute("SELECT Count(1) FROM vertices").fetchone()[0]
    assert count == nvtx     
