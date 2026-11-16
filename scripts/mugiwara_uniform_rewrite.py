#!/usr/bin/env python3
"""Mugiwara-only backport of NXNative's uniform shader compiler workarounds.

Adapted from seedds/nxnative dmsh_fetch.py/select_guards and dmsh_rewrite.py/uniform_tests.
Old pinned ABI confirms DMSH_CBSIZE_BANK=25. The newer storage-length (SBLEN) rewrite is
not included because this ABI does not define that bank.
"""
from __future__ import annotations
import collections
import re

CBSIZE_BANK = 25
_GSIZE = r'\(\(\*spvDescriptorSet0\.[a-z]+_c%d\)\._m0\[\d\]\.[xyzw] >> 2u\)' % CBSIZE_BANK
_GZERO = r'0(?:\.0|u)?'
def _gchoice(cond, read):
    return re.compile('|'.join(form % (n, cond, n, read % n, n, _GZERO) for n, form in (
        (1, r'(?<![\w>])\((?P<q%d>%s) \? (?P<r%d>%s) : (?P<z%d>%s)\)'),
        (2, r'(?P<q%d>%s) \? (?P<r%d>%s) : (?P<z%d>%s)(?![\w.])'),
    )))
_GBOOL = re.compile(r'\bbool (_\d+) = [^;\n]* < %s;' % _GSIZE)
_GROW = _gchoice(r'_\d+', r'\(\*spvDescriptorSet0\.[a-z]+_c\d+\)\._m0\[(?P<i%s>_\d+) \? [^\]\n]+ : 0\](?:\[[^\]\n]+\]|\.[xyzw])')
_GLEFT = re.compile(r'%s\) \?' % _GSIZE)

def select_guards(msl: str) -> str:
    if 'spvDescriptorSet0' not in msl: return msl
    bools = set(_GBOOL.findall(msl))
    def select(m, conds):
        n = '1' if m.group('q1') else '2'; c = m.group('q' + n)
        if c not in conds or m.group('i' + n) != c: return m.group(0)
        return 'select(%s, %s, %s)' % (m.group('z' + n), m.group('r' + n), c)
    if bools: msl = _GROW.sub(lambda m: select(m, bools), msl)
    left = _GLEFT.search(msl) or next((m for m in re.finditer(r'(?<!\[)\b(_\d+) \?', msl) if m.group(1) in bools), None)
    if left:
        line = msl[msl.rfind('\n', 0, left.start()) + 1:left.end() + 100].split('\n')[0].strip()[:160]
        raise ValueError('a bounded uniform read is not written as a select: ' + line)
    return msl

_UTEST_READ = r'as_type<(u?int)>\((\(\*spvDescriptorSet0\.[a-z]+_c(?:[3-9]|\d\d)\)\._m0\[\d+\])\.([xyzw])\)'
_UTEST = re.compile(r'(?<![\w.])%s(?= [!=]= -?\d+u?(?![\w.]))|(?<=[!=]= )%s' % (
    _UTEST_READ,
    _UTEST_READ.replace('(u?int)', '(?P<t2>u?int)').replace(r'(\(\*', r'(?P<r2>\(\*').replace('([xyzw])', '(?P<c2>[xyzw])')
))
_UTEST_LEFT = re.compile(r'(?<![\w.])-?\d+u? [!=]= $')
UWORD = ('#ifndef DM_UWORD\n#define DM_UWORD\ntemplate<typename T, int N> static inline __attribute__((always_inline)) T '
         'dm_uword(const constant vec<T, N>& v, int i) { return ((const volatile constant T*)&v)[i]; }\n#endif\n')
def _matches(msl):
    if 'spvDescriptorSet0' not in msl or 'as_type<' not in msl: return []
    def parts(m):
        if m.group(1): return m.group(1), m.group(2), m.group(3)
        if not _UTEST_LEFT.search(msl, max(0, m.start() - 16), m.start()): return None
        return m.group('t2'), m.group('r2'), m.group('c2')
    return [(m, p) for m in _UTEST.finditer(msl) for p in [parts(m)] if p]

def uniform_stats(msl):
    found = _matches(msl)
    tested = collections.Counter(r + c for _, (_, r, c) in found)
    chains = {word for word, n in tested.items() if n > 1}
    return len(chains), sum(n for word, n in tested.items() if word in chains)

def uniform_tests(msl):
    found = _matches(msl)
    tested = collections.Counter(r + c for _, (_, r, c) in found)
    chains = {word for word, n in tested.items() if n > 1}
    if not chains: return msl
    out, at = [], 0
    for m, (t, r, c) in found:
        if r + c not in chains: continue
        out += [msl[at:m.start()], 'as_type<%s>(dm_uword(%s, %d))' % (t, r, 'xyzw'.index(c))]
        at = m.end()
    body = ''.join(out) + msl[at:]
    head = re.search(r'^using namespace metal;\n', body, re.M)
    if not head: raise ValueError('uniform tests: no "using namespace metal;" to put dm_uword after')
    return body[:head.end()] + UWORD + body[head.end():]

def self_test():
    record = '(*spvDescriptorSet0.fp_c5)._m0[16]'
    size = '((*spvDescriptorSet0.fp_c25)._m0[0].x >> 2u)'
    bounded = ('using namespace metal;\n'
               'bool _5 = 3 < %s;\n'
               'float _6 = (_5 ? (*spvDescriptorSet0.fp_c5)._m0[_5 ? _7 : 0].x : 0.0);\n') % size
    selected = select_guards(bounded)
    assert 'select(0.0, (*spvDescriptorSet0.fp_c5)._m0[_5 ? _7 : 0].x, _5)' in selected, selected
    assert select_guards(selected) == selected
    source = ('using namespace metal;\n'
              'bool a = as_type<int>(%s.w) != 100;\n'
              'bool b = as_type<int>(%s.w) != 101;\n'
              'bool c = as_type<int>(%s.w) != 102;\n'
              'bool d = 103 == as_type<int>(%s.w);\n'
              'float keep = %s.x;\n') % ((record,) * 5)
    assert uniform_stats(source) == (1, 4), uniform_stats(source)
    rewritten = uniform_tests(source)
    assert rewritten.count('as_type<int>(dm_uword(%s, 3))' % record) == 4
    assert 'float keep = %s.x;' % record in rewritten
    assert rewritten.count('#define DM_UWORD') == 1
    assert uniform_tests(rewritten) == rewritten
    single = 'using namespace metal;\nbool x = as_type<int>(%s.w) != 1;\n' % record
    assert uniform_stats(single) == (0, 0) and uniform_tests(single) == single
    for bank in (0, 1, 2):
        driver = '(*spvDescriptorSet0.vp_c%d)._m0[100].y' % bank
        test = 'using namespace metal;\nbool a = as_type<int>(%s) != 0;\nbool b = as_type<int>(%s) != 1;\n' % (driver, driver)
        assert uniform_tests(test) == test
