#!/usr/bin/env python3
# coding: utf-8
#
# Copyright 2020-2022 F4PGA Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

import re


def get_scale_fs(timescale):
    """Convert sdf timescale to scale factor to femtoseconds as int

    >>> get_scale_fs('1.0 fs')
    1

    >>> get_scale_fs('1ps')
    1000

    >>> get_scale_fs('10 ns')
    10000000

    >>> get_scale_fs('10.0 us')
    10000000000

    >>> get_scale_fs('100.0ms')
    100000000000000

    >>> get_scale_fs('100 s')
    100000000000000000

    >>> try:
    ...     get_scale_fs('2s')
    ... except AssertionError as e:
    ...     print(e)
    Invalid SDF timescale 2s

    """
    mm = re.match(r'(10{0,2})(\.0)? *([munpf]?s)', timescale)
    sc_lut = {
        's': 1e15,
        'ms': 1e12,
        'us': 1e9,
        'ns': 1e6,
        'ps': 1e3,
        'fs': 1,
    }
    assert mm is not None, "Invalid SDF timescale {}".format(timescale)

    base, _, sc = mm.groups()
    return int(base) * int(sc_lut[sc])


def get_scale_seconds(timescale):
    """Convert sdf timescale to scale factor to floating point seconds

    >>> get_scale_seconds('1.0 fs')
    1e-15

    >>> get_scale_seconds('1ps')
    1e-12

    >>> get_scale_seconds('10 ns')
    1e-08

    >>> get_scale_seconds('10.0 us')
    1e-05

    >>> get_scale_seconds('100.0ms')
    0.1

    >>> round(get_scale_seconds('100 s'), 6)
    100.0
    """
    return 1e-15 * get_scale_fs(timescale)


def prepare_entry(name=None,
                  type=None,
                  from_pin=None,
                  to_pin=None,
                  from_pin_edge=None,
                  to_pin_edge=None,
                  delay_paths=None,
                  cond_equation=None,
                  is_timing_check=False,
                  is_timing_env=False,
                  is_absolute=False,
                  is_incremental=False,
                  is_cond=False):

    entry = dict()
    entry['name'] = name
    entry['type'] = type
    entry['from_pin'] = from_pin
    entry['to_pin'] = to_pin
    entry['from_pin_edge'] = from_pin_edge
    entry['to_pin_edge'] = to_pin_edge
    entry['delay_paths'] = delay_paths
    entry['is_timing_check'] = is_timing_check
    entry['is_timing_env'] = is_timing_env
    entry['is_absolute'] = is_absolute
    entry['is_incremental'] = is_incremental
    entry['is_cond'] = is_cond
    entry['cond_equation'] = cond_equation

    return entry


def add_port(portname, paths):

    name = "port_" + portname['port']
    return prepare_entry(name=name,
                         type='port',
                         from_pin=portname['port'],
                         to_pin=portname['port'],
                         delay_paths=paths)


def add_interconnect(pfrom, pto, paths):

    name = "interconnect_"
    name += pfrom['port'] + "_" + pto['port']
    return prepare_entry(name=name,
                         type='interconnect',
                         from_pin=pfrom['port'],
                         to_pin=pto['port'],
                         from_pin_edge=pfrom['port_edge'],
                         to_pin_edge=pto['port_edge'],
                         delay_paths=paths)


def add_iopath(pfrom, pto, paths):

    name = "iopath_"
    name += pfrom['port'] + "_" + pto['port']
    return prepare_entry(name=name,
                         type='iopath',
                         from_pin=pfrom['port'],
                         to_pin=pto['port'],
                         from_pin_edge=pfrom['port_edge'],
                         to_pin_edge=pto['port_edge'],
                         delay_paths=paths)


def add_device(port, paths):

    name = "device_"
    name += port['port']
    return prepare_entry(name=name,
                         type='device',
                         from_pin=port['port'],
                         to_pin=port['port'],
                         delay_paths=paths)


def add_tcheck(type, pto, pfrom, paths):

    name = type + "_"
    name += pfrom['port'] + "_" + pto['port']
    return prepare_entry(name=name,
                         type=type,
                         is_timing_check=True,
                         is_cond=pfrom['cond'],
                         cond_equation=pfrom['cond_equation'],
                         from_pin=pfrom['port'],
                         to_pin=pto['port'],
                         from_pin_edge=pfrom['port_edge'],
                         to_pin_edge=pto['port_edge'],
                         delay_paths=paths)


def add_constraint(type, pto, pfrom, paths):

    name = type + "_"
    name += pfrom['port'] + "_" + pto['port']
    return prepare_entry(name=name,
                         type=type,
                         is_timing_env=True,
                         from_pin=pfrom['port'],
                         to_pin=pto['port'],
                         from_pin_edge=pfrom['port_edge'],
                         to_pin_edge=pto['port_edge'],
                         delay_paths=paths)
