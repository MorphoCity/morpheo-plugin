-- Build ways as geometric objects
-- TESTS TO DO
-- Check that there is no more that two edges that have the same way on each place 
-- Check that there two places and only two for way on table way_partition
-- Check that there is no missing START_PL/END_PL on table ways

DELETE FROM ways;

-- Compute Way geometry (as MULTILINESTRING)

INSERT INTO ways(GEOMETRY,WAY_ID)
SELECT ST_Multi(ST_LineMerge(ST_Collect(e.GEOMETRY))), e.WAY
FROM place_edges as e 
GROUP BY e.WAY
;

-- Update start/end places
UPDATE ways SET
START_PL = (SELECT p.START_PL FROM way_partition AS p WHERE p.WAY=ways.WAY_ID AND START_PL<>0),
END_PL   = (SELECT p.END_PL   FROM way_partition AS p WHERE p.WAY=ways.WAY_ID AND END_PL<>0)
;



