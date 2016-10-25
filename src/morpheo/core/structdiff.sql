-- compute paired edges

CREATE TABLE paired(
    EDGE1 integer,
    EDGE2 integer,
    WAY1  integer,
    WAY2  integer,
    DIFF  real
);


-- Compute paired edges

INSERT INTO paired(EDGE1,EDGE2,WAY1,WAY2,DIFF)
    SELECT e1.OGC_FID,e2.OGC_FID,e1.WAY,e2.WAY,e2.ACCES - e1.ACCES 
    FROM edges1 AS e1, edges2 AS e2
    WHERE ST_Within(e1.GEOMETRY,ST_Buffer(e2.GEOMETRY,$buffersize)) 
      AND ST_Within(e2.GEOMETRY,ST_Buffer(e1.GEOMETRY,$buffersize))
    AND e1.WAY IS NOT NULL
    AND e2.WAY IS NOT NULL
    AND e1.ROWID IN (
         SELECT ROWID FROM Spatialindex
         WHERE f_table_name='edges1' AND search_frame=e2.GEOMETRY
    )
;



-- Ensure uniqueness of paired edges

CREATE UNIQUE INDEX paired_edge1_idx ON paired(EDGE1);
CREATE UNIQUE INDEX paired_edge2_idx ON paired(EDGE2);


-- Compute suppressed edges from edges1

CREATE TABLE removed(OGC_FID integer, WAY integer, LENGTH real);
CREATE TABLE added(OGC_FID integer, WAY integer, LENGTH real);

INSERT INTO removed(OGC_FID, WAY, LENGTH)
SELECT OGC_FID,WAY, LENGTH FROM edges1
WHERE OGC_FID NOT IN (SELECT EDGE1 FROM paired) AND WAY IS NOT NULL
;

INSERT INTO added(OGC_FID, WAY, LENGTH)
SELECT OGC_FID,WAY, LENGTH FROM edges2
WHERE OGC_FID NOT IN (SELECT EDGE2 FROM paired) AND WAY IS NOT NULL
;

-- Create tables for storing output

CREATE TABLE paired_edges (
    OGC_FID integer PRIMARY KEY,
    WAY1    integer,
    WAY2    integer,
    EDGE1   integer,
    EDGE2   integer,
    LENGTH  real,
    REMOVED real,
    ADDED   real,
    DELTA   real
);

SELECT AddGeometryColumn(
    'paired_edges',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM geometry_columns
        WHERE f_table_name='edges2'
    ),
    'LINESTRING',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='edges2'
    )
);

INSERT INTO paired_edges(EDGE1, EDGE2, WAY1, WAY2, LENGTH, GEOMETRY)
SELECT p.EDGE1, p.EDGE2, p.WAY1, p.WAY2, e.LENGTH, e.GEOMETRY FROM edges2 AS e, paired AS p
WHERE e.OGC_FID=p.EDGE2
;

CREATE INDEX paired_edges_idx ON paired_edges(EDGE2);


CREATE TABLE removed_edges(
    OGC_FID integer PRIMARY KEY,
    WAY integer,
    LENGTH real
);
SELECT AddGeometryColumn(
    'removed_edges',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM geometry_columns
        WHERE f_table_name='edges1'
    ),
    'LINESTRING',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='edges1'
    )
);
INSERT INTO removed_edges(OGC_FID, WAY, LENGTH, GEOMETRY)
SELECT r.OGC_FID, r.WAY, r.LENGTH, e.GEOMETRY
FROM edges1 AS e,  removed AS r
WHERE e.OGC_FID=r.OGC_FID;

CREATE TABLE added_edges(
    OGC_FID integer PRIMARY KEY,
    WAY integer,
    LENGTH real
);
SELECT AddGeometryColumn(
    'added_edges',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM geometry_columns
        WHERE f_table_name='edges2'
    ),
    'LINESTRING',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='edges2'
    )
);
INSERT INTO added_edges(OGC_FID, WAY, LENGTH, GEOMETRY)
SELECT a.OGC_FID, a.WAY, a.LENGTH, e.GEOMETRY
FROM edges2 AS e,  added AS a
WHERE e.OGC_FID=a.OGC_FID;

