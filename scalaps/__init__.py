"""
scalaps - Scala-inspired data structures for Python

Also similar to Java streams

Currently a work in progress and improvements are much appreciated
Feel free to send a PR on GitHub
"""

# Copyright 2019 Matt Hagy <matthew.hagy@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the “Software”), to deal in
# the Software without restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is furnished to do so, subject
# to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies
# or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
# FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.


import operator
import copy
from functools import reduce
from itertools import chain
from collections import defaultdict, Counter, deque
from typing import Callable, Any, Union, Iterable

__all__ = ['Seq', 'ScList', 'ScFrozenList', ]

CallableTypes = Union[Callable, str, int]
NoneType = type(None)


def identity(x):
    return x


def get_callable(obj: CallableTypes) -> Callable[[Any], Any]:
    if callable(obj):
        return obj
    elif isinstance(obj, str):
        return operator.attrgetter(obj)
    elif isinstance(obj, int):
        return operator.itemgetter(obj)
    else:
        raise TypeError(f"Can't call {obj!r}")


class IterableMixin:
    """Adds some useful Scala-inspired methods for working with iterables"""

    def tolist(self) -> 'ScList':
        return ScList(self)

    def tofrozenlist(self) -> 'ScFrozenList':
        return ScFrozenList(self)

    def todict(self) -> 'ScDict':
        return ScDict(self)

    def map(self, func_like: CallableTypes) -> 'Seq':
        return Seq(map(get_callable(func_like), self))

    def flatmap(self, func_like: CallableTypes) -> 'Seq':
        func = get_callable(func_like)
        return Seq(y for x in self for y in func(x))

    def foreach(self, func_like: CallableTypes):
        func = get_callable(func_like)
        for x in self:
            func(x)

    def take(self, n) -> 'Seq':
        return Seq(x for _, x in zip(range(n), self))

    def drop(self, n) -> 'Seq':
        def gen():
            i = iter(self)
            try:
                for _ in range(n):
                    next(i)
            except StopIteration:
                pass
            yield from i

        return Seq(gen())

    def last(self, n) -> 'Seq':
        def gen():
            d = deque()
            for x in self:
                d.append(x)
                if len(d) > n:
                    d.popleft()
            yield from d

        return Seq(gen())

    def filter(self, func_like: CallableTypes) -> 'Seq':
        return Seq(filter(get_callable(func_like), self))

    def chain(self, other) -> 'Seq':
        return Seq(chain(self, other))

    def apply(self, func):
        return get_callable(func)(self)

    def applyseq(self, func) -> 'Seq':
        return Seq(self.apply(func))

    def fold(self, init_value: Any, func_like: CallableTypes):
        return reduce(get_callable(func_like), self, init_value)

    def reduce(self, func_like: CallableTypes):
        return reduce(func_like, self)

    def sum(self):
        return sum(self)

    def count(self) -> int:
        return sum(1 for _ in self)

    def valuecounts(self) -> 'ScDict':
        return ScDict(Counter(self))

    def sortby(self, rank_func_like: CallableTypes) -> 'ScList':
        return ScList(sorted(self, key=get_callable(rank_func_like)))

    def sort(self) -> 'ScList':
        return self.sortby(identity)

    def distinct(self) -> 'ScList':
        return ScList(set(self))

    def groupby(self, key_func_like: CallableTypes) -> 'ScDict':
        key_func_like = get_callable(key_func_like)
        d = defaultdict(ScList)
        for el in self:
            d[key_func_like(el)].append(el)
        return ScDict(d)

    def keyby(self, key_func_like: CallableTypes) -> 'ScDict':
        key_func_like = get_callable(key_func_like)
        d = ScDict()
        for el in self:
            k = key_func_like(el)
            if k in d:
                raise ValueError(f"duplicate key {k!r}")
            d[k] = el
        return d

    def aggregateby(self,
                    key: CallableTypes,
                    create_aggregate: CallableTypes,
                    add_toaggregate: CallableTypes) -> 'ScDict':
        key = get_callable(key)
        create_aggregate = get_callable(create_aggregate)
        add_toaggregate = get_callable(add_toaggregate)

        aggs_by_key = {}
        for x in self:
            k = key(x)
            try:
                agg = aggs_by_key[k]
            except KeyError:
                agg = aggs_by_key[k] = create_aggregate(x)
            aggs_by_key[x] = add_toaggregate(agg, x)

        return ScDict(aggs_by_key)

    def foldby(self,
               key: CallableTypes,
               agg0,
               add_toaggregate: CallableTypes) -> 'ScDict':
        return self.aggregateby(key, lambda _: agg0, add_toaggregate)

    def reduceby(self, key: CallableTypes, reducer: CallableTypes) -> 'ScDict':
        key = get_callable(key)
        reducer = get_callable(reducer)

        existings_by_key = {}
        for x in self:
            k = key(x)
            try:
                existing = existings_by_key[k]
            except KeyError:
                existings_by_key[k] = x
            else:
                existings_by_key[k] = reducer(existing, x)

        return ScDict(existings_by_key)

    def enumerate(self):
        return Seq(enumerate(self))

    def mkstring(self, between, before='',after=''):
        return '%s%s%s' %(before,between.join(self),after)

class Seq(IterableMixin):
    """
    Wrapper around arbitrary sequences. Assumes sequences are single pass and can't be iterated
    over multiple times. Use `ScList` for realized sequences that can be iterated over multiple
    times.
    """

    def __init__(self, inner_seq: Iterable):
        self._inner_seq = inner_seq
        self._ran = False

    def __iter__(self):
        if self._ran:
            raise RuntimeError("Re-running sequence")
        self._ran = True
        try:
            return iter(self._inner_seq)
        finally:
            # remove the reference so that we can free up sources in GCing
            # while realizing the rest of the sequence of operations
            del self._inner_seq


class ListMixin:
    def __init__(self, l=()):
        self._list = l

    @property
    def length(self):
        return len(self._list)

    def reverse(self) -> Seq:
        return Seq(reversed(self._list))

    def __iter__(self):
        return iter(self._list)

    def __repr__(self):
        return f'{self.__class__.__name__}({self._list!r})'


class ScList(IterableMixin, ListMixin):
    """
    Wrapper around Python lists with a more Scala-esque API

    TODO: Add more modification methods beyond append
    """

    def __init__(self, l=()):
        super().__init__(list(l) if not isinstance(l, list) else l)

    def tolist(self):
        return self

    def append(self, x):
        self._list.append(x)
      
    def copy(self):
        return ScList(list(self._l))

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo=None):
        return ScList(copy.deepcopy(x, memo=memo) for x in self._l)


class ScFrozenList(IterableMixin, ListMixin):
    """
    Immutable wrapper around Python lists
    """

    def __init__(self, l):
        if not isinstance(l, tuple):
            l = tuple(l)
        super().__init__(l)

    def tofrozenlist(self):
        return self


class ScDict(dict):
    """
    Extension of Python dict
    """

    @property
    def length(self):
        return len(self)

    def keys(self):
        return Seq(super().keys())

    def values(self):
        return Seq(super().values())

    def items(self):
        return Seq(super().items())

    def mapvalues(self, func_like: CallableTypes) -> 'ScDict':
        func = get_callable(func_like)
        return ScDict({k: func(v) for k, v in self.items()})

    def union(self, other: Union['ScDict', dict], error_on_overlap=False):
        if error_on_overlap:
            common_keys = set(self.keys()) & set(other.keys())
            if common_keys:
                raise ValueError(f"there are {len(common_keys)} in common when non were expected")

        cp = ScDict(self)
        cp.update(other)
        return cp

    def join(self, other: 'ScDict', how='inner'):
        if how == 'inner':
            keys = set(self.keys()) & set(other.keys())
        elif how == 'outer':
            keys = set(self.keys()) | set(other.keys())
        elif how == 'left':
            keys = self.keys()
        elif how == 'right':
            keys = other.keys()
        else:
            raise ValueError(f"Invalid join {how!r}. Must be either inner, outer, left or right")

        def gen():
            for key in keys:
                yield key, (self.get(key), other.get(key))

        return Seq(gen())
