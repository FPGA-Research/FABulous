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

from .ply import lex

input_data = ""

reserved = {
    'DELAYFILE': 'DELAYFILE',
    'SDFVERSION': 'SDFVERSION',
    'DESIGN': 'DESIGN',
    'VENDOR': 'VENDOR',
    'PROGRAM': 'PROGRAM',
    'VERSION': 'VERSION',
    'TIMESCALE': 'TIMESCALE',
    'CELL': 'CELL',
    'CELLTYPE': 'CELLTYPE',
    'INSTANCE': 'INSTANCE',
    'DELAY': 'DELAY',
    'ABSOLUTE': 'ABSOLUTE',
    'INCREMENT': 'INCREMENT',
    'IOPATH': 'IOPATH',
    'posedge': 'POSEDGE',
    'negedge': 'NEGEDGE',
    'SETUP': 'SETUP',
    'HOLD': 'HOLD',
    'REMOVAL': 'REMOVAL',
    'RECOVERY': 'RECOVERY',
    'TIMINGCHECK': 'TIMINGCHECK',
    'DIVIDER': 'DIVIDER',
    'DATE': 'DATE',
    'VOLTAGE': 'VOLTAGE',
    'PROCESS': 'PROCESS',
    'TEMPERATURE': 'TEMPERATURE',
    'TIMINGENV': 'TIMINGENV',
    'PATHCONSTRAINT': 'PATHCONSTRAINT',
    'INTERCONNECT': 'INTERCONNECT',
    'PORT': 'PORT',
    'SETUPHOLD': 'SETUPHOLD',
    'WIDTH': 'WIDTH',
    'COND': 'COND',
    'DEVICE': 'DEVICE',
}

operators = (
    'ARITHMETIC',
    'MODULO',
    'LOGIC_NOT',
    'BIT_NOT',
    'LOGIC_AND',
    'BIT_AND',
    'NAND',
    'LOGIC_OR',
    'BIT_OR',
    'NOR',
    'XOR',
    'XNOR',
    'EQUAL',
    'NEQUAL',
    'CASEEQUAL',
    'CASENEQUAL',
    'LEFTSHIFT',
    'RIGHTSHIFT',
    'GT',
    'LT',
    'GTE',
    'LTE',
)

tokens = (
    'LPAR',
    'RPAR',
    'ASTERISK',
    'DOT',
    'SLASH',
    'COLON',
    'FLOAT',
    'SCALARCONSTANT',
    'QFLOAT',
    'QSTRING',
    'STRING',
) + tuple(reserved.values()) + operators

t_ARITHMETIC = r'[\+\-\*]'
t_MODULO = r'%'
t_LOGIC_NOT = r'!'
t_BIT_NOT = r'~'
t_LOGIC_AND = r'&&'
t_BIT_AND = r'&'
t_NAND = r'~&'
t_LOGIC_OR = r'\|\|'
t_BIT_OR = r'\|'
t_NOR = r'~\|'
t_XOR = r'\^'
t_XNOR = r'~\^|\^~'
t_EQUAL = r'=='
t_NEQUAL = r'!='
t_CASEEQUAL = r'==='
t_CASENEQUAL = r'!=='
t_LEFTSHIFT = r'<<'
t_RIGHTSHIFT = r'>>'
t_GT = r'>'
t_GTE = r'>='
t_LT = r'<'
t_LTE = r'<='


t_LPAR = r'\('
t_RPAR = r'\)'
t_COLON = r':'
t_QFLOAT = r'\"[-+]?(?: [0-9]+)(?: \.[0-9]+)\"'
t_QSTRING = r'\"[a-zA-Z0-9_!#$%&\'()*+,\-./:;<=>?@\[\\\]^`{|}~ \t\n]+\"'

t_ignore = ' \t'


# define FLOAT&SCALARCONSTANT as function so they take precendence over STRING
def t_SCALARCONSTANT(t):
    r"[01]?'[Bb][01]"
    return t


def t_FLOAT(t):
    r'[-]?\.?[0-9]+(\.[0-9]+)?'
    return t


# the same for dot and slash
def t_DOT(t):
    r'\.'
    return t


def t_ASTERISK(t):
    r'\*'
    return t


def t_SLASH(t):
    r'\/'
    return t


# OLD STRING rule causing problems
# with tokens like $
#def t_STRING(t):
#    r'[a-zA-Z0-9_\/.\[\]\\]+'
#    t.type = reserved.get(t.value, 'STRING')
#    return t
def t_STRING(t):
    # Unquoted identifiers / instance names / nets
    # Allowed chars:
    #   - letters, digits, underscore
    #   - $, /, ., [, ], \
    r'[a-zA-Z0-9_\$/.\[\]\\]+'
    t.type = reserved.get(t.value, 'STRING')
    return t


def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)


def t_error(t):
    raise Exception("Illegal character '%s' in line %d, column %d"
                    % (t.value[0], t.lineno, find_column(input_data, t)))

# Compute column.
# input is the input text string
# token is a token instance


def find_column(input, token):
    line_start = input.rfind('\n', 0, token.lexpos) + 1
    return (token.lexpos - line_start) + 1


lexer = lex.lex()
