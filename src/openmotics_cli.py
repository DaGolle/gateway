# Copyright (C) 2020 OpenMotics BV
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import absolute_import, print_function
import argparse
import logging
import sys
import os

import constants
import gateway

logger = logging.getLogger('openmotics')


def cmd_factory_reset(args):
    lock_file = constants.get_init_lockfile()
    if os.path.isfile(lock_file) and not args.force:
        print('already_in_progress')
        exit(1)
    with open(lock_file, 'w') as fd:
        fd.write('factory_reset')


parser = argparse.ArgumentParser()
parser.add_argument('--version', action='version', version=gateway.__version__)
subparsers = parser.add_subparsers()
operator_parser = subparsers.add_parser('operator')
operator_subparsers = operator_parser.add_subparsers()
factory_reset_parser = operator_subparsers.add_parser('factory-reset')
factory_reset_parser.set_defaults(func=cmd_factory_reset)
factory_reset_parser.add_argument('--force', action='store_true')


def main():
    args = parser.parse_args()
    logger.addHandler(logging.StreamHandler(sys.stderr))
    logger.setLevel(logging.INFO)
    args.func(args)


if __name__ == '__main__':
    main()
