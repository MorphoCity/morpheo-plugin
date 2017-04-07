-- Import edge table from one database to another
-- WARNING this should

ATTACH DATABASE '$srcdb' AS srcdb;

CREATE TABLE edges${sfx}(
   OGC_FID   integer PRIMARY KEY,
   NAME      text default NULL,
   LENGTH    real,
   DEGREE    integer,
   WAY       integer,
    -- Indicators
    -- Note: because data will be exported to 
    -- shapefile our names have to be compliant
    -- to the limition of the dbf format (less than 10 chars)
    CLOSEN           real, -- closeness
    SPACING          real, -- spacing
    ORTHOG           real, -- orthogonality
    BETWEE           real, -- betweeness
    USE              real, -- stress centrality
    RTOPO            real, -- topological radius (from ways)
    ACCES            real, -- accessibility      (from ways)
    -- Classes 
    DEGREE_CL        integer,
    LENGTH_CL        integer,
    CLOSEN_CL        integer,
    SPACING_CL       integer,
    ORTHOG_CL        integer,
    BETWEE_CL        integer,
    USE_CL           integer
);

SELECT AddGeometryColumn(
    'edges${sfx}',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM srcdb.geometry_columns
        WHERE f_table_name='place_edges'
    ),
    'LINESTRING',
    (
        SELECT coord_dimension
        FROM srcdb.geometry_columns
        WHERE f_table_name='place_edges'
    )
);


SELECT CreateSpatialIndex('edges${sfx}', 'GEOMETRY');

INSERT INTO edges${sfx} (OGC_FID, NAME, LENGTH, DEGREE, WAY, GEOMETRY, ACCES)

SELECT OGC_FID, NAME, LENGTH, DEGREE, WAY, GEOMETRY, ACCES
FROM srcdb.place_edges
;

-- Copy places


CREATE TABLE places${sfx}(
    OGC_FID integer PRIMARY KEY,
    DEGREE  integer DEFAULT 0,
    USER_PL integer DEFAULT 0  -- Set to 0 if computed, 1 if imported, 
);

SELECT AddGeometryColumn(
    'places${sfx}',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM srcdb.geometry_columns
        WHERE f_table_name='places'
    ),
    'POLYGON',
    (
        SELECT coord_dimension
        FROM srcdb.geometry_columns
        WHERE f_table_name='places'
    )
);

SELECT CreateSpatialIndex('places${sfx}', 'GEOMETRY');

INSERT INTO places${sfx} ( OGC_FID, GEOMETRY )
SELECT OGC_FID, GEOMETRY
FROM srcdb.places
;

DETACH DATABASE 'srcdb';

