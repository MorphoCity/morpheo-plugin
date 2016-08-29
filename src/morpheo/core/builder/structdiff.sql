-- compute paired edges

CREATE TABLE paired(
    EDGE1 integer,
    EDGE2 integer,
    WAY1  integer,
    WAY2  integer,
    DIFF  real
); 



-- Compute tolerance buffers from edges1

CREATE TABLE buf1 (
    OGC_FID integer PRIMARY KEY,
    WAY     integer,
    ACCES real
);

SELECT AddGeometryColumn(
    'buf1',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM geometry_columns
        WHERE f_table_name='edges1'
    ),
    'POLYGON',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='edges1'
    )
);

SELECT CreateSpatialIndex('buf1', 'GEOMETRY');

INSERT INTO buf1(OGC_FID, ACCES, WAY, GEOMETRY) 
SELECT OGC_FID, ACCES, WAY, ST_Buffer(GEOMETRY, $buffersize) FROM edges1
;

-- Compute tolerance buffers from edges2

CREATE TABLE buf2(
    OGC_FID integer PRIMARY KEY,
    WAY     integer,
    ACCES real
);

SELECT AddGeometryColumn(
    'buf2',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM geometry_columns
        WHERE f_table_name='edges2'
    ),
    'POLYGON',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='edges2'
    )
);

SELECT CreateSpatialIndex('buf2', 'GEOMETRY');

INSERT INTO buf2(OGC_FID, ACCES, WAY, GEOMETRY) 
SELECT OGC_FID, ACCES, WAY, ST_Buffer(GEOMETRY, $buffersize) FROM edges2
;

-- Compute paired edges

INSERT INTO paired(EDGE1,EDGE2,WAY1,WAY2,DIFF)
SELECT e1.OGC_FID,e2.OGC_FID,e1.WAY,e2.WAY,e2.ACCES - e1.ACCES FROM buf1 AS e1, buf2 AS e2 
WHERE ST_Within(e1.GEOMETRY,e2.GEOMETRY) AND ST_Within(e2.GEOMETRY,e1.GEOMETRY)
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

-- Create table for storing output

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

