# -*- encoding=utf-8 -*-
""" Partition tools 
"""
from collections import namedtuple
import numpy as np


def create_partition( size ):
    """ Init a partition table
        by assigning each element to its
        own equivalence class
    """
    return np.arange(size)


def resolve( table, k, j ):
    """ Assign k and j to the same partition

        :return: the index of the partition
    """
    while table[j]!=j: 
        j=table[j]
    while table[k]!=k:
        k=table[k]
    if j!=k:
        table[max(j,k)]=min(j,k)
    return min(j,k)


def update( table ):
    """ Update partition

        This function has to be called after 
        multiple calls to resolve: it shuffles the partition
        table in order to assign the corroect partition index
        to all elements from the same equivalent class
    """
    for j in range(len(table)):
        while table[j] != table[table[j]]:
            table[j] = table[table[j]]


def num_partitions( table ):
    """ Return the number of equivalence classes.
    """
    n = 1
    m = table[0]
    for j in range(len(table)):
        if m < table[j]:
            m = table[j]
            n = n+1
    return n


Matrix = namedtuple('Matrix', ('elems','values','nullvalue'))


def create_matrix( elems, fun, nullvalue=9999999):
    """ Create a matrix object

        :param elems: array of elements
        :param fun: initialisatiton function, return a value for a
                    given pair of elements.
        :param default: default value
        :return: an object holding pair values
    """
    n = len(elems)
    values = np.full((n,n),nullvalue)
    for i in xrange(n-1):
        for j in xrange(i+1,n):
           value = fun( elems[i], elems[j] )
           values[i,j] = value
    return Matrix(elems, values, nullvalue)


def get_argmin_index( matrix ):
    """ Return the indices of element that hold the
        minimum value

        :param matrix: A Matrix object 
    """
    idx = np.argmin(matrix.values) 
    return np.unravel(np.argmin(y), y.shape)


def pop_argmin( m ):
    """ Return the pair of elements that hold the
        minimum value and remove that pair of elements
    """
    n = len(m.elemes)
    while n > 1:
        i,j = get_argmin_index(m)
        e1,e2,v = m.elems[i],m.elems[j]
        m.values[i,:] = m.nullvalue
        m.values[:,j] = m.nullvalue
        yield e1, e2, v
        n = n-2
        

def get_value( m, e1, e2 ):
    """ Return the value of a pair of element
    """
    i1 = m.elems.index(e1)
    i2 = m.elems.index(e2)
    return m.values[min(i1,i2),max(i1,i2)] 


def angle_from_azimuth( az1, az2 ):
    """ Compute angle between two azimuths
    """
    angle = abs(az1-az2)
    if angle > np.pi:
        angle = 2*np.pi - angle
    return abs( angle - np.pi )

   

