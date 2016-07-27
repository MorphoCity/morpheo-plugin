""" Test ways
"""

def test_endpoints_places(conn):
    """ Test that there is no null start/end places for ways
    """
    rows = conn.execute("SELECT OGC_FID FROM ways WHERE START_PL IS NULL OR END_PL IS NULL").fetchall()
    rows = [r[0] for r in rows]
    assert len(rows)==0, "Found ways with start/end places {}".format(rows if len(rows)<=10 else "(%d ways !)" % len(rows))


def test_positive_degree(conn):
    """ Test that all ways have positive degree
    """
    rows = conn.execute("SELECT OGC_FID FROM ways WHERE degree=0").fetchall()
    rows = [r[0] for r in rows]
    assert len(rows)==0, "Found ways with null degree {}".format(rows)


def test_positive_connectiviti(conn):
    """ Test that all ways have positive degree
    """
    rows = conn.execute("SELECT OGC_FID FROM ways WHERE connectivity=0").fetchall()
    rows = [r[0] for r in rows]
    assert len(rows)==0, "Found ways with null connectivity {}".format(rows)
 
