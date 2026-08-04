# SPDX-License-Identifier: BSD-3-Clause

class SMTSolverOptions:
    def __init__(self,
                 sweep_seed: int,
                 sweep_threads: int,
                 solver_timeout_ms: int,
                 use_bit_vec: bool,
                 bit_vec_width: int):
        self.sweep_seed = sweep_seed
        self.sweep_threads = sweep_threads
        self.solver_timeout_ms = solver_timeout_ms
        self.use_bit_vec = use_bit_vec
        self.bit_vec_width = bit_vec_width
