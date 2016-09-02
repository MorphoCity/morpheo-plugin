# -*- encoding=utf-8 -*-
""" Graph algorithms
"""

from __future__ import print_function

import random
import networkx as nx
from itertools import izip
from networkx.algorithms.centrality.betweenness import (_single_source_shortest_path_basic,
                                                        _single_source_dijkstra_path_basic,
                                                        _rescale)

def stress_centrality( G, k=None, normalized=True, weight=None, endpoints=False, seed=None ):
    """ Compute stress centrality 

        We use the same BSF algorithm as for beteweeness centrality 
        used in networkx, but we change the accumulating phase
        in order to get only the number of shortests path

        see algorithm 12 in http://algo.uni-konstanz.de/publications/b-vspbc-08.pdf
    """
    stress = dict.fromkeys(G, 0.0)  # b[v]=0 for v in G
    if k is None:
        nodes = G
    else:
        random.seed(seed)
        nodes = random.sample(G.nodes(), k)
    for s in nodes:
        # single source shortest paths
        if weight is None:  # use BFS
            S, P, sigma = _single_source_shortest_path_basic(G, s)
        else:  # use Dijkstra's algorithm
            S, P, sigma = _single_source_dijkstra_path_basic(G, s, weight)
        # accumulation
        if endpoints:
            stress = _accumulate_stress_endpoints(stress, S, P, sigma, s)
        else:
            stress = _accumulate_stress_basic(stress, S, P, sigma, s)
    # rescaling
    stress = _rescale(stress, len(G),
                      normalized=normalized,
                      directed=G.is_directed(),
                      k=k)
    return stress


# Helpers for stress centrality

def _accumulate_stress_basic(stress, S, P, sigma, s):
    delta = dict.fromkeys(S, 0)
    while S:
        w = S.pop()
        for v in P[w]:
            delta[v] += (1.0+delta[w])
        if w != s:
            stress[w] += sigma[w]*delta[w]
    return stress


def _accumulate_stress_endpoints(stress, S, P, sigma, s):
    stress[s] += len(S) - 1
    delta = dict.fromkeys(S, 0)
    while S:
        w = S.pop()
        for v in P[w]:
            delta[v] += (1.0+delta[w])
        if w != s:
            stress[w] += sigma[w]*delta[w] + 1
    return stress


def multiple_sources_shortest_path_length( G, sources, cutoff=None ):
    """ Compute shortest path length from a set of sources

        The algorithm is the same as the BFS algorithme used in
        networkx.single_source_shortest_path_length except that it takes 
        a several set of source as starting point.

        :param G: Networkx Graph
        :param sources: list of starting nodes
        :param cutoff: optional. Only path of length >= cutoff are
                       returned

        :return: lengths : Dictionary of shorterts path lengths keyed by target
    """
    seen={}                  # level (number of hops) when seen in BFS
    level=0                  # the current level
    nextlevel=dict.fromkeys(sources,1)  # dict of nodes to check at next level
    while nextlevel:
        thislevel=nextlevel  # advance to next level
        nextlevel={}         # and start a new list (fringe)
        for v in thislevel:
            if v not in seen:
                seen[v]=level # set the level of vertex v
                nextlevel.update(G[v]) # add neighbors of v
        if (cutoff is not None and cutoff <= level):  break
        level=level+1
    return seen  # return all path lengths as dictionary


def shortest_subgraph_path( G, source, target, mesh, weight=None ):
    """ Compute shortest path using subgraph shortcuts

        A mesh is a set of nodes that are considered topologically equivalent
        for the shortest path computation
    """
    from itertools import combinations

    # Compute subgraph set
    subgraphs = list(nx.connected_component_subgraphs(mesh))

    # Add shortcuts to the graph
    Gs = G.copy()  

    # Remove all nodes in nbunch
    #Gs.remove_nodes_from(nbunch)

    EPSILON_WEIGHT=0.01

    # Create shortcuts

    for i, g in enumerate(subgraphs):
        # Skip subgraph with only one node
        if g.order()==1: 
           continue
        # Get the fringe of the node group in G
        edges = list(combinations([v for v in g if any(n not in g for n in G[v])], 2))
        # Add shortcuts between all nodes from the fringe
        if weight is None:
            Gs.add_edges_from(edges, index=i)
        else:
            Gs.add_weighted_edges_from(((u,v,EPSILON_WEIGHT) for u,v in edges), weight=weight, index=i)

    # Resolve shortest_path
    p = nx.shortest_path(Gs, source, target, weight=weight)

    # Resolve shortcuts
    path = [source]
    for u,v in izip(p[:-1],p[1:]):
       # Test if edge is a shortcut
       if Gs.is_multigraph():
            index = Gs[u][v][0].get('index')
       else:
            index = Gs[u][v]['index']
       if index is not None:
           # compute real path inside that subgraph
           path = path + nx.shortest_path(subgraphs[index],u,v,weight=weight)[1:]
       else:
           path.append(v)
    
    return path


