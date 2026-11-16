#!/usr/bin/env python3
"""Mugiwara-only backport of NXNative's uniform-tests Metal compiler workaround.

Adapted verbatim at the algorithm/regex level from seedds/nxnative
dm/gfx/tools/dmsh_rewrite.py at a0cad7e06a0821c52477ff20dbc53d6126748c54.
The rewrite changes only repeated equality tests of a single game uniform word.
"""
from __future__ import annotations

import collections
import re


_UTEST_READ = r'as_type<(u?int)>\((\(\*spvDescriptorSet0\.[a-z]+_c(?:[3-9]|\d\d)\)\._m0\[\d+\])\.([xyzw])\)'  # game slots c3 and up, not driver's banks
_UTEST = re.compile(
    r'(?<![\w.])%s(?= [!=]= -?\d+u?(?![\w.]))|(?<=[!=]= )%s'
    % (
        _UTEST_READ,
        _UTEST_READ.replace('(u?int)', '(?P<t2>u?int)')
        .replace(r'(\(\*', r'(?P<r2>\(\*')
        .replace('([xyzw])', '(?P<c2>[xyzw])'),
    )
)
_UTEST_LEFT = re.compile(r'(?<![\w.])-?\d+u? [!=]= $')
UWORD = (
    '#ifndef DM_UWORD\n#define DM_UWORD\n'
    'template<typename T, int N> static inline __attribute__((always_inline)) T '
    'dm_uword(const constant vec<T, N>& v, int i) '
    '{ return ((const volatile constant T*)&v)[i]; }\n#endif\n'
)


def _matches(msl: str):
    if 'spvDescriptorSet0' not in msl or 'as_type<' not in msl:
        return []
    def parts(match):
        if match.group(1):
            return match.group(1), match.group(2), match.group(3)
        if not _UTEST_LEFT.search(msl, max(0, match.start() - 16), match.start()):
            return None
        return match.group('t2'), match.group('r2'), match.group('c2')
    return [(match, part) for match in _UTEST.finditer(msl)
            for part in [parts(match)] if part]


def uniform_stats(msl: str) -> tuple[int, int]:
    found = _matches(msl)
    tested = collections.Counter(record + component
                                 for _, (_, record, component) in found)
    chains = {word for word, count in tested.items() if count > 1}
    return len(chains), sum(count for word, count in tested.items() if word in chains)


def uniform_tests(msl: str) -> str:
    """Make every test in a repeated uniform-word equality chain a volatile load."""
    found = _matches(msl)
    tested = collections.Counter(record + component
                                 for _, (_, record, component) in found)
    chains = {word for word, count in tested.items() if count > 1}
    if not chains:
        return msl
    output, at = [], 0
    for match, (kind, record, component) in found:
        if record + component not in chains:
            continue
        output += [
            msl[at:match.start()],
            'as_type<%s>(dm_uword(%s, %d))'
            % (kind, record, 'xyzw'.index(component)),
        ]
        at = match.end()
    body = ''.join(output) + msl[at:]
    head = re.search(r'^using namespace metal;\n', body, re.M)
    if not head:
        raise ValueError('uniform tests: no "using namespace metal;" to put dm_uword after')
    return body[:head.end()] + UWORD + body[head.end():]


def self_test() -> None:
    """Small synthetic regression copied from NXNative's upstream test shape."""
    word = '(*spvDescriptorSet0.fp_c5)._m0[16]'
    source = (
        'using namespace metal;\n'
        'bool a = as_type<int>(%s.w) != 100;\n'
        'bool b = as_type<int>(%s.w) != 101;\n'
        'bool c = as_type<int>(%s.w) != 102;\n'
        'bool d = 103 == as_type<int>(%s.w);\n'
        'float keep = %s.x;\n'
    ) % ((word,) * 5)
    assert uniform_stats(source) == (1, 4), uniform_stats(source)
    rewritten = uniform_tests(source)
    assert rewritten.count('as_type<int>(dm_uword(%s, 3))' % word) == 4
    assert 'float keep = %s.x;' % word in rewritten
    assert rewritten.count('#define DM_UWORD') == 1
    assert uniform_tests(rewritten) == rewritten
    single = 'using namespace metal;\nbool x = as_type<int>(%s.w) != 1;\n' % word
    assert uniform_stats(single) == (0, 0)
    assert uniform_tests(single) == single
    drivers = []
    for bank in (0, 1, 2):
        driver = '(*spvDescriptorSet0.vp_c%d)._m0[100].y' % bank
        drivers.append('bool a = as_type<int>(%s) != 0;\nbool b = as_type<int>(%s) != 1;\n' % (driver, driver))
    for driver_source in drivers:
        assert uniform_tests('using namespace metal;\n' + driver_source) == 'using namespace metal;\n' + driver_source
