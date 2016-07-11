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

INSERT INTO edges(GEOMETRY, LENGTH)
SELECT GEOMETRY, GLength(GEOMETRY)
FROM $input_table
;

-- Create the vertices of the graph

INSERT INTO vertices(GEOMETRY)
SELECT StartPoint( GEOMETRY ) AS GEOMETRY FROM edges
UNION
SELECT EndPoint( GEOMETRY ) AS GEOMETRY FROM edges
;


-- Create the vertices of the graph

-- Fill up vertices table

INSERT INTO vertices(GEOMETRY)
SELECT StartPoint( GEOMETRY ) AS GEOMETRY FROM edges
UNION
SELECT EndPoint( GEOMETRY ) AS GEOMETRY FROM edges
;

-- Edges connectivity
-- Set edges connectivity

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

-- -----------------------------------------------------------
-- Create places schema
-- Places are created from buffers and from external geometries

CREATE TABLE places(
    OGC_FID integer primary key,
    DEGREE integer default 0
);

SELECT AddGeometryColumn(
    'places',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    ),
    'POLYGON',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('places', 'GEOMETRY');

 
-- Create an assoction table betwween vertices and places
-- This table is faster to build than using subquery/join with 

CREATE TABLE place_vtx(
    VERTEX REFERENCES vertices(OGC_FID),
    PLACE  REFERENCES places(OGC_FID)
);

CREATE INDEX place_vtx_idx ON place_vtx(VERTEX);


-- Create edge table computed between places intead of vertices
-- This will be the starting point for ways

CREATE TABLE place_edges(
   OGC_FID  integer PRIMARY KEY,
   EDGE      REFERENCES edges(OGC_FID),
   START_PL  REFERENCES places(OGC_FID),
   END_PL    REFERENCES places(OGC_FID),
   START_VTX REFERENCES vertices(OGC_FID),  -- for optimizing join 
   END_VTX   REFERENCES vertices(OCG_FID), -- for optimizing join
   START_AZ double,
   END_AZ   double,
   WAY      integer
);

SELECT AddGeometryColumn(
    'place_edges',
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

SELECT CreateSpatialIndex('place_edges', 'GEOMETRY');
CREATE INDEX place_edges_start_pl_idx   ON place_edges(START_PL);
CREATE INDEX place_edges_end_pl_idx     ON place_edges(END_PL);
CREATE INDEX place_edges_edge_idx       ON place_edges(EDGE);
CREATE INDEX place_edges_start_vtx_idx  ON place_edges(START_VTX);
CREATE INDEX place_edges_end_vtx_idx    ON place_edges(END_VTX);


-- Create angles table
-- The angle table references angles between couples of edges that have one end in the same place

CREATE TABLE angles(
    OGC_FID integer PRIMARY KEY,
    PLACE   integer REFERENCES places(OGC_FID),
    EDGE1   integer REFERENCES place_edges(OGC_FID),
    EDGE2   integer REFERENCES place_edges(OGC_FID),
    ANGLE   double,
    COEFF   double
);    





