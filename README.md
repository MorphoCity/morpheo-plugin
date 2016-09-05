# Morpheo: python package and plugin QGIS for the characterization of spatial graphs.


## References:

* Claire Lagesse's PhD thesis: https://halshs.archives-ouvertes.fr/tel-01245898

# Requirements:

* QGIS 2.14 minimum (with spatialite 4.2.1+ enabled)
* GDAL/OGR tools

# Install as command line:

```bash
python setup.py 
```

From this, Moprpheo will ba available as command line, i.e:

```bash
morpheo --help
```

# Install as QGIS plugin

Copy the 



## What's computed

* Viary geometries as topological graph (arcs and vertices)
* Places 
* Ways
* Orhogonality, topological radius, centrality indicators on edges and ways
* Horizon from mesh structures
* Shortest/simplest path
* Shortest/simplest path with topological shortcuts from mesh structures.
* Way simplest path (simplest path in way line graph)
* Structural differences

## Graph indicators

Indicators computed on ways and arcs:

    CONN             real, -- connectivity
    CLOSEN           real, -- closeness
    SPACING          real, -- spacing
    ORTHOG           real, -- orthogonality
    BETWEE           real, -- betweeness
    USE              real, -- stress centrality
    RTOPO            real, -- topological radius
    ACCES            real, -- accessibility


## Tables computed

These are the tables computed in the working database of morpheo: these table
can be accessed in qgis for debug purpose.

* edges: edges of the topological graph computed from initial data
* vertices: vertices of the topological graph command from initial data
* places: places buffers computed, including external places definitions. These
          or vertices of edges in  'place_edges'
* place_edges: edges beteween places. All indicators and path are computed using these edges.
* ways: computed ways from place_edges
* shortest: last shortest computed path 
* simplest: last shortest computed path
* azimuth: last azimuthal path
* mesh_shortest: last computed shortest path using structural mesh as topological shortcut
* mesh_simplest: last computed simplest path using structucal mesh as topological shortcut
* way_simplest: last computed path on ways using the simplest path in the way's line graph. 
* paired_edges: Computed invariants edges between two graphs (structural diff)
 






