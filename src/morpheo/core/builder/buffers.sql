-- Create places from buffers

-- Create a temporary table to store union of buffers

CREATE TABLE $buffer_table(OGC_FID integer primary key);

SELECT AddGeometryColumn(
    '$buffer_table',
    'GEOMETRY',
    (
        SELECT CAST(srid AS integer)
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    ),
    'MULTIPOLYGON',
    (
        SELECT coord_dimension
        FROM geometry_columns
        WHERE f_table_name='$input_table'
    )
);

SELECT CreateSpatialIndex('$buffer_table', 'GEOMETRY');

