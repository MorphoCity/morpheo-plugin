# -*- encoding=utf-8 -*-
""" Partition tools 
"""
from collections import namedtuple
from numpy import pi
from math import atan2
import numpy as np

#-------------------------------
# Partition
#-------------------------------

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


def get_index_table( table ):
    """ Create a mapping index table
    """
    sz = len(table)
    itable = np.full(sz,0,dtype=int)
    m = table[0]
    n = 0
    for j in range(sz):
        if m < table[j]:
            m = table[j]
            n = n+1
            itable[j] = n
        elif m > table[j]:
            itable[j] = itable[table[j]]
        else:
            itable[j] = n

    return itable

#-------------------------------
# Pair matrix 
#-------------------------------

Matrix = namedtuple('Matrix', ('elems','values','nullvalue'))


def create_matrix( elems, fun, nullvalue=9999999.0):
    """ Create a matrix object

        :param elems: array of elements
        :param fun: initialisatiton function, return a value for a
                    given pair of elements.
        :param default: default value
        :return: an object holding pair values
    """
    n = len(elems)
    values = np.full((n,n),nullvalue)
    for i in range(n-1):
        for j in range(i+1,n):
           value = fun( elems[i], elems[j] )
           values[i,j] = value
    return Matrix(elems, values, nullvalue)


def get_argmin_index( m ):
    """ Return the indices of element that hold the
        minimum value

        :param m: A Matrix object 
    """
    idx = np.argmin(m.values) 
    return np.unravel_index(idx, m.values.shape)


def next_argmin( m ):
    """ iterate through indices in ascending order
    """
    while True:
        i, j = get_argmin_index(m)
        v = m.values[i,j]
        if v == m.nullvalue: break
        m.values[i,j] = m.nullvalue
        yield i,j


def pop_args( m, i1, i2 ):
    """ Pop a pair of element
    """
    m.elems[i1] = None
    m.elems[i2] = None
    m.values[[i1,i2],:] = m.nullvalue
    m.values[:,[i1,i2]] = m.nullvalue
        

def get_remaining_elements( m ):
    """ Return remaining elements (not paired)
    """
    return filter(None, m.elems)


def get_value( m, i1, i2 ):
    """ Return the value of a pair of element
    """
    return m.values[min(i1,i2),max(i1,i2)] 


def angle_from_azimuth( az1, az2 ):
    """ Compute angle between two azimuths
    """
    angle = abs(az1-az2)
    if angle > pi:
        angle = 2*pi - angle
    return abs( angle - pi )


def azimuth(x1,y1,x2,y2):
    """ Compute azimuth between two directions
    """
    return atan2(x2-x1, y2-y1)

