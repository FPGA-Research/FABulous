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


def gen_timing_entry(entry):

    if entry['min'] is None and entry['avg'] is None\
            and entry['max'] is None:
        # if all the values are None return empty timing
        return "()"

    return "({MIN}:{AVG}:{MAX})".format(
        MIN=entry['min'],
        AVG=entry['avg'],
        MAX=entry['max'])


def emit_timingenv_entries(delays):

    entries = ""
    tenv_entries = ""
    for delay in sorted(delays):
        delay = delays[delay]
        entry = ""
        if not delay['is_timing_env']:
            # handle only timing_env here
            continue

        input_str = ""
        output_str = ""
        if delay['to_pin_edge'] is not None:
            output_str = "(" + delay['to_pin_edge'] + " "\
                + delay['to_pin'] + ")"
        else:
            output_str = delay['to_pin']

        if delay['from_pin_edge'] is not None:
            input_str = "(" + delay['from_pin_edge'] + " "\
                + delay['from_pin'] + ")"
        else:
            input_str = delay['from_pin']

        entry += """
                (PATHCONSTRAINT {output} {input} {RISE} {FALL})""".format(
            output=output_str,
            input=input_str,
            RISE=gen_timing_entry(delay['delay_paths']['rise']),
            FALL=gen_timing_entry(delay['delay_paths']['fall']))
        entries += entry

    if entries != "":
        tenv_entries += """
        (TIMINGENV"""
        tenv_entries += entries
        tenv_entries += """
        )"""

    return tenv_entries


def emit_timingcheck_entries(delays):

    entries = ""
    tcheck_entries = ""
    for delay in sorted(delays):
        delay = delays[delay]
        entry = ""
        if not delay['is_timing_check']:
            # handle only timing checks here
            continue

        input_str = ""
        output_str = ""
        if delay['to_pin_edge'] is not None:
            output_str = "(" + delay['to_pin_edge'] + " "\
                + delay['to_pin'] + ")"
        else:
            output_str = delay['to_pin']

        if delay['from_pin_edge'] is not None:
            input_str = "(" + delay['from_pin_edge'] + " "\
                + delay['from_pin'] + ")"
        else:
            input_str = delay['from_pin']

        if delay['is_cond']:
            input_str = "(COND {equation} {input})".format(
                equation=delay['cond_equation'],
                input=input_str)

        if delay['name'].startswith("width"):
            output_str = ""

        if delay['name'].startswith("setuphold"):
            entry += """
                ({type} {output} {input} {SETUP} {HOLD})""".format(
                type=delay['type'].upper(),
                input=input_str,
                output=output_str,
                SETUP=gen_timing_entry(delay['delay_paths']['setup']),
                HOLD=gen_timing_entry(delay['delay_paths']['hold']))

        else:
            entry += """
                ({type} {output} {input} {NOMINAL})""".format(
                type=delay['type'].upper(),
                input=input_str,
                output=output_str,
                NOMINAL=gen_timing_entry(delay['delay_paths']['nominal']))
        entries += entry

    if entries != "":
        tcheck_entries += """
        (TIMINGCHECK"""
        tcheck_entries += entries
        tcheck_entries += """
        )"""

    return tcheck_entries


def emit_delay_entries(delays):

    entries_absolute = ""
    entries_incremental = ""
    entries = ""

    for delay in sorted(delays):
        entry = ""
        delay = delays[delay]
        if not delay['is_absolute'] and not delay['is_incremental']:
            # if it's neiter absolute, nor incremental
            # it must be a timingcheck entry. It will be
            # handled later
            continue

        input_str = ""
        output_str = ""
        if delay['to_pin_edge'] is not None:
            output_str = "(" + delay['to_pin_edge'] + " "\
                + delay['to_pin'] + ")"
        else:
            output_str = delay['to_pin']

        if delay['from_pin_edge'] is not None:
            input_str = "(" + delay['from_pin_edge'] + " "\
                + delay['from_pin'] + ")"
        else:
            input_str = delay['from_pin']

        tim_val_str = ""

        for path in ['fast', 'nominal', 'slow']:
            if path in delay['delay_paths']:
                tim_val_str += gen_timing_entry(delay['delay_paths'][path])

        indent = ""
        if delay['type'].startswith("port"):
            entry += """
                (PORT {input} {timval})""".format(
                input=input_str,
                timval=tim_val_str)
        elif delay['type'].startswith("interconnect"):
            entry += """
                (INTERCONNECT {input} {output} {timval})""".format(
                input=input_str,
                output=output_str,
                timval=tim_val_str)
        elif delay['type'].startswith("device"):
            entry += """
                (DEVICE {input} {timval})""".format(
                input=input_str,
                timval=tim_val_str)
        else:
            if delay['is_cond']:
                indent = "     "
                entry += """
                (COND ({equation})""".format(
                    equation=delay['cond_equation'])

            entry += """
                {indent}(IOPATH {input} {output} {timval})""".format(
                indent=indent,
                input=input_str,
                output=output_str,
                timval=tim_val_str)

            if delay['is_cond']:
                entry += """
                    )"""
        if delay['is_absolute']:
            entries_absolute += entry
            # if it is not absolute it must be incremental
            # all the other types are filtered above
        else:
            entries_incremental += entry

    if entries_absolute != "" or entries_incremental != "":
        entries += """
        (DELAY"""
    if entries_absolute != "":
        entries += """
            (ABSOLUTE"""
        entries += entries_absolute
        entries += """
            )"""
    if entries_incremental != "":
        entries += """
            (INCREMENT"""
        entries += entries_incremental
        entries += """
            )"""
    if entries_absolute != "" or entries_incremental != "":
        entries += """
        )"""

    return entries


def emit_sdf(timings, timescale='1ps', uppercase_celltype=False):

    for slice in timings:
        sdf = \
            """(DELAYFILE
    (SDFVERSION \"3.0\")
    (TIMESCALE {})
""".format(timescale)
        if 'cells' in timings:
            for cell in sorted(timings['cells']):
                for location in sorted(timings['cells'][cell]):

                    if uppercase_celltype:
                        celltype = cell.upper()
                    else:
                        celltype = cell

                    sdf += """
    (CELL
        (CELLTYPE \"{name}\")""".format(name=celltype)

                    sdf += """
        (INSTANCE {location})""".format(location=location)
                    sdf += emit_delay_entries(
                        timings['cells'][cell][location])
                    sdf += emit_timingcheck_entries(
                        timings['cells'][cell][location])
                    sdf += emit_timingenv_entries(
                        timings['cells'][cell][location])
                    sdf += """
    )"""
        sdf += """
)"""

    # fix "None" entries
    sdf = sdf.replace("None", "")
    return sdf
