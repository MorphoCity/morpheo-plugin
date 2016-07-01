-- Create topological graph from input data

-- vertices

CREATE TABLE vertices(
    OGC_FID integer PRIMARY KEY,
    DEGREE integer DEFAULT 0
);

SELECT AddGeometryColumn(
    'vertices', 
    'GEOMETRY', 
    (
        SELECT CAST(srid AS integer) 
        FROM geometry_columns 
        WHERE f_table_name='$input_table'
    ), 
    'POINT', 
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('vertices', 'GEOMETRY');

-- Edges

CREATE TABLE edges(
    OGC_FID integer PRIMARY KEY REFERENCES $input_table(OGC_FID),
    START_VTX integer REFERENCES vertices(OGC_FID),
    END_VTX integer REFERENCES vertices(OGC_FID),
    LENGTH real,
    DEGREE integer DEFAULT 0,
    NAME text default NULL
);

SELECT AddGeometryColumn( -- to ease update, because joins are not allowed
    'edges', 
    'GEOMETRY', 
    (
        SELECT CAST(srid AS integer) 
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    ), 
    'LINESTRING',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('edges', 'GEOMETRY');
CREATE INDEX edges_start_vtx_idx ON edges(START_VTX);
CREATE INDEX edges_end_vtx_idx ON edges(END_VTX);
CREATE INDEX edges_name_idx ON edges(NAME);

-- Copy edges from origin table

SELECT 'Initialze edges table geometries';

INSERT INTO edges(GEOMETRY, LENGTH)
SELECT GEOMETRY, GLength(GEOMETRY)
FROM $input_table
;

-- Create the vertices of the graph

SELECT 'Fill up vertices table';

INSERT INTO vertices(GEOMETRY)
SELECT StartPoint( GEOMETRY ) AS GEOMETRY FROM edges
UNION
SELECT EndPoint( GEOMETRY ) AS GEOMETRY FROM edges
;


-- Create the vertices of the graph

SELECT 'Fill up vertices table';

INSERT INTO vertices(GEOMETRY)
SELECT StartPoint( GEOMETRY ) AS GEOMETRY FROM edges
UNION
SELECT EndPoint( GEOMETRY ) AS GEOMETRY FROM edges
;

-- Edges connectivity

SELECT 'Set edges connectivity';

UPDATE edges 
SET END_VTX = 
(
    SELECT v.OGC_FID 
    FROM vertices AS v
    WHERE Intersects( v.GEOMETRY, EndPoint( edges.GEOMETRY ) )
    AND
    v.ROWID IN (
      SELECT ROWID FROM SpatialIndex 
      WHERE f_table_name='vertices' AND search_frame=edges.GEOMETRY)
),
START_VTX = 
(
    SELECT v.OGC_FID 
    FROM vertices AS v
    WHERE Intersects( v.GEOMETRY, StartPoint( edges.GEOMETRY ) )
    AND
    v.ROWID IN (
      SELECT ROWID FROM SpatialIndex 
      WHERE f_table_name='vertices' AND search_frame=edges.GEOMETRY)
)
;

-- Update vertices degree

SELECT 'Set vertices degree';

UPDATE vertices 
SET DEGREE = 
(
    SELECT COUNT(1) 
    FROM edges 
    WHERE edges.END_VTX = vertices.OGC_FID 
    OR edges.START_VTX = vertices.OGC_FID
)
;

UPDATE vertices 
SET DEGREE = vertices.DEGREE + -- add one to the count for each loops touching the vertex
(
    SELECT COUNT(1) 
    FROM edges 
    WHERE edges.END_VTX = vertices.OGC_FID 
    AND edges.START_VTX = vertices.OGC_FID
)
;


-- Update edges degree

SELECT 'Set edges degree';

UPDATE edges 
SET DEGREE = 
        (SELECT DEGREE FROM vertices WHERE vertices.OGC_FID = edges.START_VTX)
       +(SELECT DEGREE FROM vertices WHERE vertices.OGC_FID = edges.END_VTX)
       - 2
    WHERE edges.START_VTX != edges.END_VTX
;

UPDATE edges 
SET DEGREE = 
        (SELECT DEGREE FROM vertices WHERE vertices.OGC_FID = edges.START_VTX)
       - 2
    WHERE edges.START_VTX == edges.END_VTX
;


