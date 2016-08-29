# -*- encoding=utf-8 -*-
""" Graph algorithms
"""

import random
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




