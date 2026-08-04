# SPDX-License-Identifier: BSD-3-Clause

import os
import sys

# Add subpackages to the module search path
stomp_dir = os.path.dirname(os.path.abspath(__file__))
subpackages_dir = os.path.join(stomp_dir, "subpackages")
if subpackages_dir not in sys.path:
    sys.path.insert(0, subpackages_dir)
