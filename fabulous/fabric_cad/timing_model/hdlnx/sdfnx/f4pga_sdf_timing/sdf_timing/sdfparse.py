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

from . import sdflex
from . import sdfyacc
from . import sdfwrite


def init():
    sdfyacc.timings = dict()

    sdfyacc.header = dict()
    sdfyacc.delays_list = list()
    sdfyacc.cells = dict()

    sdfyacc.tmp_delay_list = list()
    sdfyacc.tmp_equation = list()
    sdfyacc.tmp_constr_list = list()

    sdflex.lexer.lineno = 1


def emit(input, timescale='1ps'):
    return sdfwrite.emit_sdf(input, timescale)


def parse(input):
    init()
    sdflex.input_data = input
    sdfyacc.parser.parse(sdflex.input_data)
    return sdfyacc.timings
