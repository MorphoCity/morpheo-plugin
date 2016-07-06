-- Creates way hypergraph

-- Ways

CREATE TABLE ways( 
    OGC_FID integer PRIMARY KEY,
    LENGTH real,
    NB_EDGES integer,
    NB_VERTICES integer, 
    DEGREE integer, -- nb of intersecting ways
);

SELECT AddGeometryColumn(
    'ways', 
    'GEOMETRY', 
    (
        SELECT CAST(srid AS integer) 
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    ), 
    'MULTILINESTRING',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('ways', 'GEOMETRY');

-- Way - vertices association

CREATE TABLE ways_vertices(
    OGC_FID integer PRIMARY KEY,
    WAY integer REFERENCES ways(OGC_FID),
    VTX integer REFERENCES vertices(OGC_FID)
);

CREATE INDEX ways_vertices_way_idx ON ways_vertices(WAY);
CREATE INDEX ways_vertices_vtx_idx ON ways_vertices(VTX);


-- Way - Way association table

CREATE TABLE ways_ways(
    OGC_FID integer PRIMARY KEY,
    WAY1 integer REFERENCES ways(OGC_FID),
    WAY2 integer REFERENCES ways(OGC_FID)
);

CREATE INDEX ways_ways_way1_idx ON ways_ways(WAY1);
CREATE INDEX ways_ways_way2_idx ON ways_ways(WAY2);




