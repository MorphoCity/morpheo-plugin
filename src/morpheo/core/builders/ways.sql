-- Build ways as geometric objects

DELETE FROM ways;

-- Compute Way geometry (as MULTILINESTRING)

INSERT INTO ways(GEOMETRY,WAY_ID)
SELECT ST_Multi(ST_LineMerge(ST_Collect(e.GEOMETRY))), e.WAY
FROM place_edges as e 
GROUP BY e.WAY
;

