# -*- coding: utf-8 -*-
# Author: Florian Mayer <florian.mayer@bitsrc.org>
#
# This module was developed with funding provided by
# the ESA Summer of Code (2011).
#
# pylint: disable=C0103,R0903

from __future__ import absolute_import

from datetime import datetime

from sunpy.net.attr import (
    Attr, ValueAttr, AttrWalker, AttrAnd, AttrOr, DummyAttr, ValueAttr
)
from sunpy.util.util import to_angstrom
from sunpy.util.multimethod import MultiMethod
from sunpy.time import parse_time

TIMEFORMAT = '%Y%m%d%H%M%S'

class _Range(object):
    def __init__(self, min_, max_, create):
        self.min = min_
        self.max = max_
        self.create = create
    
    def __xor__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        
        new = DummyAttr()
        if self.min < other.min:            
            new |= self.create(self.min, min(other.min, self.max))
        if other.max < self.max:
            new |= self.create(other.max, self.max)
        return new
    
    def __contains__(self, other):
        return self.min <= other.min and self.max >= other.max


class Wave(Attr, _Range):
    def __init__(self, wavemin, wavemax, waveunit='Angstrom'):
        self.min, self.max = sorted(
            to_angstrom(v, waveunit) for v in [wavemin, wavemax]
        )
        self.unit = 'Angstrom'
        
        Attr.__init__(self)
        _Range.__init__(self, self.min, self.max, self.__class__)
    
    def collides(self, other):
        return isinstance(other, self.__class__)


class Time(Attr, _Range):
    def __init__(self, start, end, near=None):
        self.start = parse_time(start)
        self.end = parse_time(end)
        self.near = None if near is None else parse_time(near)

        _Range.__init__(self, self.start, self.end, self.__class__)
        Attr.__init__(self)
    
    def collides(self, other):
        return isinstance(other, self.__class__)
    
    def __xor__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError
        if self.near is not None or other.near is not None:
            raise TypeError
        return _Range.__xor__(self, other)
    
    def pad(self, timedelta):
        return Time(self.start - timedelta, self.start + timedelta)
    
    def __repr__(self):
        return '<Time(%r, %r, %r)>' % (self.start, self.end, self.near)


class Extent(Attr):
    # pylint: disable=R0913
    def __init__(self, x, y, width, length, type_):
        Attr.__init__(self)
        
        self.x = x
        self.y = y
        self.width = width
        self.length = length
        self.type = type_
    
    def collides(self, other):
        return isinstance(other, self.__class__)


class Field(ValueAttr):
    def __init__(self, fielditem):
        ValueAttr.__init__(self, {
            ('field', 'fielditem'): fielditem
        })


class _VSOSimpleAttr(Attr):
    def __init__(self, value):
        Attr.__init__(self)
        
        self.value = value
    
    def collides(self, other):
        return isinstance(other, self.__class__)
    
    def __repr__(self):
        return "<%s(%r)>" % (self.__class__.__name__, self.value)


class Provider(_VSOSimpleAttr):
    pass


class Source(_VSOSimpleAttr):
    pass


class Instrument(_VSOSimpleAttr):
    pass


class Physobs(_VSOSimpleAttr):
    pass


class Pixels(_VSOSimpleAttr):
    pass


class Level(_VSOSimpleAttr):
    pass


class Resolution(_VSOSimpleAttr):
    pass


class Detector(_VSOSimpleAttr):
    pass


class Filter(_VSOSimpleAttr):
    pass


class Sample(_VSOSimpleAttr):
    pass


class Quicklook(_VSOSimpleAttr):
    pass


class PScale(_VSOSimpleAttr):
    pass


# The walker specifies how the Attr-tree is converted to a query the
# server can handle.
walker = AttrWalker()

@walker.add_creator(ValueAttr, AttrAnd)
# pylint: disable=E0102,C0103,W0613
def _create(wlk, root, api):
    """ Implementation detail. """
    value = api.factory.create('QueryRequestBlock')
    wlk.apply(root, api, value)
    return [value]

@walker.add_applier(ValueAttr)
# pylint: disable=E0102,C0103,W0613
def _apply(wlk, root, api, queryblock):
    """ Implementation detail. """
    for k, v in root.attrs.iteritems():
        lst = k[-1]
        rest = k[:-1]
        
        block = queryblock
        for elem in rest:
            block = block[elem]
        block[lst] = v

@walker.add_applier(AttrAnd)
# pylint: disable=E0102,C0103,W0613
def _apply(wlk, root, api, queryblock):
    """ Implementation detail. """
    for attr in root.attrs:
        wlk.apply(attr, api, queryblock)

@walker.add_creator(AttrOr)
# pylint: disable=E0102,C0103,W0613
def _create(wlk, root, api):
    """ Implementation detail. """
    blocks = []
    for attr in root.attrs:
        blocks.extend(wlk.create(attr, api))
    return blocks

@walker.add_creator(DummyAttr)
# pylint: disable=E0102,C0103,W0613
def _create(wlk, root, api):
    """ Implementation detail. """
    return api.factory.create('QueryRequestBlock')

@walker.add_applier(DummyAttr)
# pylint: disable=E0102,C0103,W0613
def _apply(wlk, root, api, queryblock):
    """ Implementation detail. """
    pass

walker.add_converter(Extent)(
    lambda x: ValueAttr(
        dict((('extent', k), v) for k, v in vars(x).iteritems())
    )
)

walker.add_converter(Time)(
    lambda x: ValueAttr({
            ('time', 'start'): x.start.strftime(TIMEFORMAT),
            ('time', 'end'): x.end.strftime(TIMEFORMAT) ,
            ('time', 'near'): (
                x.near.strftime(TIMEFORMAT) if x.near is not None else None),
    })
)

walker.add_converter(_VSOSimpleAttr)(
    lambda x: ValueAttr({(x.__class__.__name__.lower(), ): x.value})
)

walker.add_converter(Wave)(
    lambda x: ValueAttr({
            ('wave', 'wavemin'): x.min,
            ('wave', 'wavemax'): x.max,
            ('wave', 'waveunit'): x.unit,
    })
)

# The idea of using a multi-method here - that means a method which dispatches
# by type but is not attached to said class - is that the attribute classes are
# designed to be used not only in the context of VSO but also elsewhere (which
# AttrAnd and AttrOr obviously are - in the HEK module). If we defined the
# filter method as a member of the attribute classes, we could only filter
# one type of data (that is, VSO data).
filter_results = MultiMethod(lambda *a, **kw: (a[0], ))

# If we filter with ANDed together attributes, the only items are the ones
# that match all of them - this is implementing  by ANDing the pool of items
# with the matched items - only the ones that match everything are there
# after this.
@filter_results.add_dec(AttrAnd)
def _(attr, results):
    res = set(results)
    for elem in attr.attrs:
        res &= filter_results(elem, res)
    return res

# If we filter with ORed attributes, the only attributes that should be
# removed are the ones that match none of them. That's why we build up the
# resulting set by ORing all the matching items.
@filter_results.add_dec(AttrOr)
def _(attr, results):
    res = set()
    for elem in attr.attrs:
        res |= filter_results(elem, results)
    return res

# Filter out items by comparing attributes.
@filter_results.add_dec(_VSOSimpleAttr)
def _(attr, results):
    attrname = attr.__class__.__name__.lower()
    return set(
        item for item in results
        # Some servers seem to obmit some fields. No way to filter there.
        if not hasattr(item, attrname) or
        getattr(item, attrname).lower() == attr.value.lower()
    )

# The dummy attribute does not filter at all.
@filter_results.add_dec(DummyAttr, Field)
def _(attr, results):
    return set(results)


@filter_results.add_dec(Wave)
def _(attr, results):
    return set(
        it for it in results
        if
        attr.min <= to_angstrom(it.wave.wavemax, it.wave.waveunit)
        and
        attr.max >= to_angstrom(it.wave.wavemin, it.wave.waveunit)
    )

@filter_results.add_dec(Time)
def _(attr, results):
    return set(
        it for it in results
        if
        attr.min <= datetime.strptime(it.time.end, TIMEFORMAT)
        and
        attr.max >= datetime.strptime(it.time.start, TIMEFORMAT)
    )

@filter_results.add_dec(Extent)
def _(attr, results):
    return set(
        it for it in results
        if it.extent.type.lower() == attr.type.lower()
    )
